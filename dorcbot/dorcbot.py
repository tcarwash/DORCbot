import os
import discord
import re
import requests
import threading
import time
from dotenv import load_dotenv
from tabulate import tabulate
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from . import kc2g, shared
from .reminders import ReminderStore, parse_schedule_time
from .callsigns import CallsignStore
from .kisschat_bridge import KissChatBridge

load_dotenv(Path(__file__).with_name(".env"))
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dorcbot")

TOKEN = os.environ.get("TOKEN")
HAMQTH_CALLSIGN = os.environ.get("HAMQTH_CALLSIGN")
HAMQTH_PASSWORD = os.environ.get("HAMQTH_PASSWORD")
DORC_CALLSIGNS = sorted({
    call.strip().upper()
    for call in os.environ.get("DORC_CALLSIGNS", "").split(",")
    if call.strip()
})
REMINDER_DB_PATH = os.environ.get(
    "REMINDER_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "reminders.sqlite3"),
)
reminders = ReminderStore(REMINDER_DB_PATH)
callsign_store = CallsignStore(REMINDER_DB_PATH)
KISSCHAT_BRIDGE_TOKEN = os.environ.get("KISSCHAT_BRIDGE_TOKEN", "")
kisschat_bridge = KissChatBridge(
    None, REMINDER_DB_PATH, KISSCHAT_BRIDGE_TOKEN,
    host=os.environ.get("KISSCHAT_BRIDGE_HOST", "0.0.0.0"),
    port=int(os.environ.get("KISSCHAT_BRIDGE_PORT", "8765")),
)

HAMQTH_API = "https://www.hamqth.com/api/v2"
_hamqth_token = None
_hamqth_token_expires = 0
_hamqth_token_lock = threading.Lock()
_data_cache = {}
_data_cache_lock = threading.Lock()

intents = discord.Intents.default()
intents.members = True
# Enable the privileged gateway intent only when legacy prefix commands are
# requested. Slash commands work without Message Content access.
intents.message_content = os.environ.get("ENABLE_PREFIX_COMMANDS", "false").lower() in {
    "1", "true", "yes", "on"
}
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


@client.event
async def setup_hook():
    kisschat_bridge.client = client
    await kisschat_bridge.start()
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        logger.info("Synced %d application commands to Discord guild %s", len(synced), guild_id)
    else:
        synced = await tree.sync()
        logger.info("Synced %d global application commands", len(synced))
    asyncio.create_task(reminder_dispatcher())


async def reminder_dispatcher():
    """Deliver due reminders and keep recurring net times in local time."""
    while not client.is_closed():
        now = datetime.now(timezone.utc)
        for reminder in await asyncio.to_thread(reminders.due, now):
            start_local = datetime.fromisoformat(reminder["local_start"])
            start_utc = start_local.replace(
                tzinfo=ZoneInfo(reminder["timezone"])
            ).astimezone(timezone.utc)
            if now >= start_utc + timedelta(minutes=2):
                # Skip stale notifications after downtime; advance weekly nets.
                await asyncio.to_thread(reminders.delivered, reminder)
                continue
            try:
                channel = client.get_channel(reminder["channel_id"])
                if channel is None:
                    channel = await client.fetch_channel(reminder["channel_id"])
                stamp = int(start_utc.timestamp())
                repeat = " (weekly)" if reminder["recurrence"] == "weekly" else ""
                await channel.send(
                    f"📻 **Reminder{repeat}: {reminder['title']}**\n"
                    f"Starts <t:{stamp}:F> (<t:{stamp}:R>).",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                await asyncio.to_thread(reminders.delivered, reminder)
            except Exception:
                logger.exception("Could not deliver reminder %s", reminder["id"])
                await asyncio.to_thread(reminders.failed, reminder["id"])
        await asyncio.sleep(30)

# Command map & help columns
COMMANDMAP_FUNC = 0
COMMANDMAP_SHORT_HELP = 1
COMMANDMAP_LONG_HELP_FUNC = 2


class Payload:
    def __init__(self, fmt="codeblock", content="", delete_after=60):
        self.fmt = fmt
        self.content = content
        self.delete_after = delete_after

    def to_dict(self):
        # List of attributes not to send to Discord
        keep = [
            "content",
            "tts",
            "embed",
            "file",
            "files",
            "nonce",
            "allowed_mentions",
            "reference",
            "mention_author",
        ]

        arg_dict = {k: self.__dict__[k] for k in keep if k in self.__dict__}

        return arg_dict

    def format_block(self):
        if self.fmt == "codeblock":
            self.content = f"```{self.content}```"

        return True

    def send(self):
        self.format_block()
        arg_dict = self.to_dict()

        return arg_dict


def error(description):
    payload = Payload(fmt="")
    payload.embed = discord.Embed(color=0xFF5733, title="Error:")
    payload.embed.description = description
    payload.embed.set_thumbnail(
        url="https://c.tenor.com/OxvVRFnPZO8AAAAM/error-the-simpsons.gif"
    )

    return payload


def usercall(user):
    callsign = nickname_callsign(user)
    if callsign:
        return calldata(callsign)
    else:
        return None


def nickname_callsign(user):
    """Use the second nickname word as the callsign, matching the /muf convention."""
    words = getattr(user, "display_name", "").split()
    if len(words) < 2:
        return None
    candidate = words[1].upper()
    match = shared.isvalidcallformat(candidate)
    return candidate if match and match.group(0) == candidate else None


def cached_json(key, url, params=None, ttl=60):
    now = time.monotonic()
    with _data_cache_lock:
        cached = _data_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    with _data_cache_lock:
        _data_cache[key] = (now + ttl, data)
    return data


def hamqth_token(force_refresh=False):
    global _hamqth_token, _hamqth_token_expires
    if not HAMQTH_CALLSIGN or not HAMQTH_PASSWORD:
        raise RuntimeError(
            "Callbook lookup needs a free HamQTH account configured with "
            "HAMQTH_CALLSIGN and HAMQTH_PASSWORD."
        )
    with _hamqth_token_lock:
        if not force_refresh and _hamqth_token and time.monotonic() < _hamqth_token_expires:
            return _hamqth_token
        response = requests.post(
            f"{HAMQTH_API}/login",
            json={"callsign": HAMQTH_CALLSIGN, "password": HAMQTH_PASSWORD},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        _hamqth_token = result["token"]
        _hamqth_token_expires = time.monotonic() + int(result.get("expiresIn", 3600)) - 60
        return _hamqth_token


def calldata(callsign):
    if not HAMQTH_CALLSIGN or not HAMQTH_PASSWORD:
        return None
    callsign = callsign.split(";")[0].strip().upper()
    response = requests.get(
        f"{HAMQTH_API}/callbook/{requests.utils.quote(callsign, safe='')}",
        params={"app": "DORCbot"},
        headers={"Authorization": f"Bearer {hamqth_token()}"},
        timeout=15,
    )
    if response.status_code == 401:
        response = requests.get(
            f"{HAMQTH_API}/callbook/{requests.utils.quote(callsign, safe='')}",
            params={"app": "DORCbot"},
            headers={"Authorization": f"Bearer {hamqth_token(force_refresh=True)}"},
            timeout=15,
        )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    record = response.json()
    return {
        "call": record.get("callsign", callsign),
        "aliases": record.get("aliases"),
        "name": record.get("name"),
        "fname": record.get("nick"),
        "country": record.get("country"),
        "state": (record.get("region") or {}).get("usState"),
        "grid": (record.get("location") or {}).get("grid"),
    }


def dxcc(query):
    query = query.split(";")[0].strip().upper()
    if not query:
        return None
    param = "entity" if query.isdigit() else "callsign"
    record = cached_json(
        f"dxcc:{param}:{query}",
        f"{HAMQTH_API}/dxcc",
        {param: query},
        ttl=86400,
    )
    entity = record.get("entity") or {}
    return {
        "dxcc": entity.get("adif"),
        "name": entity.get("name") or record.get("details"),
        "continent": record.get("continent") or entity.get("continent"),
        "ituzone": record.get("itu") or entity.get("itu"),
        "cqzone": record.get("waz") or entity.get("waz"),
        "timezone": record.get("utcOffset"),
    }


def get_dxcc(payload, query, *args):
    data = dxcc(query.split()[0])
    if data:
        payload.content = f"DXCC Data for {query.upper()} (HamQTH)\n\n"
        payload.content += f"DXCC Number: {data.get('dxcc')}\n"
        payload.content += f"Country: {data.get('name')}\n"
        payload.content += f"Continent: {data.get('continent')}\n"
        payload.content += f"ITU Zone: {data.get('ituzone')}\n"
        payload.content += f"CQ Zone: {data.get('cqzone')}\n"
        payload.content += f"Time Zone: {data.get('timezone')}"
    else:
        payload = error(
            f"API returned no result for dxcc matching: {query.upper()}"
        )

    return payload


def get_calldata(payload, callsign, *args):
    if not HAMQTH_CALLSIGN or not HAMQTH_PASSWORD:
        public_data = dxcc(callsign.split()[0])
        if not public_data:
            return error("No public DXCC information found for that callsign.")
        payload.content = f"Public HamQTH DXCC data for {callsign.upper()}\n\n"
        payload.content += f"Country/entity: {public_data.get('name')}\n"
        payload.content += f"Continent: {public_data.get('continent')}\n"
        payload.content += f"ITU zone: {public_data.get('ituzone')}\n"
        payload.content += f"CQ zone: {public_data.get('cqzone')}\n\n"
        payload.content += (
            "Configure a free HamQTH account to see full callbook profile and grid data."
        )
        return payload
    data = calldata(callsign.split()[0])
    if data:
        payload.content = f"Data for {data.get('call', callsign.upper())} (HamQTH)\n\n"
        payload.content += (
            f"Callsign: {data.get('call', callsign.upper())} [ Aliases: {data.get('aliases') or 'none'} ]\n"
        )
        payload.content += f"Name: {data.get('name') or 'not listed'}\n"
        payload.content += f"Country: {data.get('country') or 'not listed'}\n"
        payload.content += f"State: {data.get('state') or 'not listed'}\n"
        payload.content += f"Grid: {data.get('grid') or 'not listed'}"
    else:
        payload = error(
            "No HamQTH callbook result. Callbook lookup requires a free HamQTH account."
        )

    return payload


def get_spots(payload, query="", member_callsigns=None, *args):
    callsigns = sorted(set(DORC_CALLSIGNS).union(member_callsigns or []))
    if not callsigns:
        return error("No member callsigns found. Add a callsign to member nicknames or use /callsign set.")
    if len(callsigns) > 30:
        return error("HamQTH supports at most 30 callsigns per spots request.")
    calls = ",".join(callsigns)
    response = cached_json(
        f"spots:{calls}",
        f"{HAMQTH_API}/spots",
        {"calls": calls, "limit": 200},
        ttl=60,
    )
    spots = response.get("spots", []) if isinstance(response, dict) else []
    payload.content = "Recent spots of DORC members (data provided by HamQTH):\n\n"
    table = [
        [
            spot.get("dxcall", "?"),
            spot.get("freq", "?"),
            spot.get("mode") or "?",
            spot.get("spotter", "?"),
            spot.get("time", "?"),
        ]
        for spot in spots[:5]
    ]
    if table:
        payload.content += tabulate(
            table, ["Call", "kHz", "mode", "spotted by", "time UTC"]
        )
    else:
        payload.content += "No recent spots found for the configured member callsigns."

    return payload


def _latest_measurement(data, value_keys):
    """Read the latest useful value from NOAA's JSON object or row formats."""
    if isinstance(data, dict):
        for key in value_keys:
            value = data.get(key)
            if value not in (None, ""):
                return data.get("time_tag", data.get("time")), value
        rows = data.get("data")
        if rows is not None:
            data = rows
    if not isinstance(data, list):
        return None, None

    rows = []
    if data and isinstance(data[0], list):
        headers = [str(value).lower() for value in data[0]]
        rows = [dict(zip(headers, row)) for row in data[1:] if isinstance(row, list)]
    else:
        rows = [row for row in data if isinstance(row, dict)]
    for row in reversed(rows):
        lowered = {str(key).lower(): value for key, value in row.items()}
        value = next(
            (lowered[key] for key in value_keys if lowered.get(key) not in (None, "")),
            None,
        )
        if value is not None:
            return lowered.get("time_tag", lowered.get("time")), value
    return None, None


def get_solar(payload, *args):
    flux_data = cached_json(
        "noaa:solar-flux",
        "https://services.swpc.noaa.gov/json/solar-radio-flux.json",
        ttl=300,
    )
    kp_data = cached_json(
        "noaa:planetary-k",
        "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
        ttl=300,
    )
    flux_time, flux = _latest_measurement(flux_data, ("adjusted", "flux", "sfi"))
    kp_time, kp = _latest_measurement(kp_data, ("kp_index", "kp", "k"))
    payload.content = "Current solar data (NOAA Space Weather Prediction Center):\n\n"
    rows = []
    if flux is not None:
        rows.append(["Solar radio flux (10.7 cm)", flux, flux_time or ""])
    if kp is not None:
        rows.append(["Planetary K index", kp, kp_time or ""])
    if rows:
        payload.content += tabulate(rows, ["Index", "Value", "As of UTC"])
    else:
        payload = error("NOAA returned no current solar readings.")

    return payload


def get_muf(payload, query, *args):
    query = query.split()
    if len(query) == 2:
        loc_from = query[0]
        loc_to = query[1]
    else:
        user_call = usercall(payload.author)
        if len(query) == 1 and user_call:
            loc_from = user_call["grid"]
            loc_to = query[0]
        else:
            payload = error("Invalid input. Try !help muf for usage")
            return payload
    # validate griddiness. If no gridditude, assume it's a callsign
    #   If no grid is available, it will come back blank and fail the check below.
    try:
        if not shared.isvalidgrid(loc_from) and shared.isvalidcallformat(
            loc_from
        ):
            lookup_from = loc_from
            loc_from = callsign_grid(loc_from)
            if loc_from is None:
                raise ValueError(f"Unable to find a grid for {lookup_from}")

        if not shared.isvalidgrid(loc_to) and shared.isvalidcallformat(loc_to):
            lookup_to = loc_to
            loc_to = callsign_grid(loc_to)
            if loc_to is None:
                raise ValueError(f"Unable to find a grid for {lookup_to}")

        if shared.isvalidgrid(loc_from) and shared.isvalidgrid(loc_to):
            payload.content = f"MUF from {loc_from.upper()} to {loc_to.upper()}:\n(Courtesy of KC2G/prop.kc2g.com)\n\n"
            muf = kc2g.muf(loc_from, loc_to)
            tab = []
            header = ["MUF Short Path", "MUF Long Path"]
            row = [muf["muf_sp"], muf["muf_lp"]]
            tab.append(row)
            payload.content = payload.content + tabulate(tab, header)
        else:
            raise ValueError
    except ValueError as e:
        payload = error(str(e))
    return payload


def muf_usage():
    return """
    Get MUF (courtesy of KC2G / prop.kc2g.org)

    Returns the latest Maximum Usable Frequency between two grid squares via long & short paths.

    If a callsign is used for one or both locators, bot will attempt to find the operator's home grid via the HamQTH callbook.

    If your server display name is in the exact format "Name Callsign" i.e. "Tyler AG7SU" or "displayname AG7SU"
    you may omit a starting grid to use the grid associated with your callsign on HamQTH. e.g. `!muf W1AW`

    """


def callsign_grid(callsign):
    callsigndata = calldata(callsign)
    if (
        callsigndata
        and "grid" in callsigndata.keys()
        and len(callsigndata["grid"]) > 0
    ):
        return callsigndata["grid"]
    else:
        return None


def get_help(payload, query, *args):
    # Dynamically create help based on the defined commands (commandmap)
    query = query.split()
    payload.content = "Usage: "
    if len(query) == 0:
        for key in commandmap.keys():
            command = (
                "\n\t"
                + key
                + " -- "
                + commandmap.get(key)[COMMANDMAP_SHORT_HELP]
            )
            payload.content += command
    else:
        # Help on a specific command
        # Show regular help if advanced is not available
        if query[0].startswith("!"):
            commandname = query[0]
        else:
            commandname = "!" + query[0]
        if commandname in commandmap.keys():
            command = (
                "\n\t"
                + query[0]
                + " -- "
                + commandmap.get(commandname)[COMMANDMAP_SHORT_HELP]
            )
            payload.content += command
            if len(commandmap.get(commandname)) > COMMANDMAP_LONG_HELP_FUNC:
                payload.content += (
                    "\n\t"
                    + commandmap.get(commandname)[COMMANDMAP_LONG_HELP_FUNC]()
                )
        else:
            payload.content = (
                f"Command {commandname} not found. Try !help instead."
            )
    return payload


# Add commands here. Format:
#    '!command': [function_to_create_final_output], "Help text", detailed_usage_function_name
commandmap = {
    "!spots": [get_spots, "Get recent spots for DORC callsigns"],
    "!solar": [get_solar, "Get solar conditions"],
    "!call": [get_calldata, "Get callsign info '!call <callsign>'"],
    "!dxcc": [get_dxcc, "Get dxcc info '!dxcc <query>'"],
    "!muf": [
        get_muf,
        "Get maximum observed frequency between "
        "grid squares or callsigns '!muf <from_locator> <to_locator>'",
        get_muf,
    ],
    "!help": [
        get_help,
        "Get the thing you're reading now. Use !help <command> for detailed help, if available.",
    ],
}


async def send_command_result(interaction, function, query="", *args):
    """Run a blocking data lookup away from Discord's event loop."""
    payload = Payload()
    payload.author = interaction.user
    try:
        payload = await asyncio.to_thread(function, payload, query, *args)
        if interaction.response.is_done():
            await interaction.edit_original_response(**payload.send())
        else:
            await interaction.response.send_message(**payload.send())
    except Exception:
        # Keep service details and credentials out of public Discord messages.
        logger.exception("Slash command %s failed", function.__name__)
        message = "That lookup failed. Please try again in a moment."
        if interaction.response.is_done():
            await interaction.edit_original_response(content=message, embeds=[])
        else:
            await interaction.response.send_message(message, ephemeral=True)


@tree.command(name="spots", description="Show recent spots for DORC callsigns")
async def slash_spots(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    member_callsigns = []
    if interaction.guild is not None:
        try:
            members = [member async for member in interaction.guild.fetch_members(limit=None)]
            registered = await asyncio.to_thread(
                callsign_store.list_for_guild, interaction.guild_id
            )
            for member in members:
                if member.bot:
                    continue
                callsign = registered.get(member.id) or nickname_callsign(member)
                if callsign:
                    member_callsigns.append(callsign)
        except Exception:
            logger.exception("Could not collect callsigns for guild %s", interaction.guild_id)
            await interaction.edit_original_response(
                content=(
                    "I couldn't read the server member list. Enable the Guild Members intent "
                    "for DORCbot in the Discord Developer Portal, then restart it."
                ),
                embeds=[],
            )
            return
    await send_command_result(interaction, get_spots, "", member_callsigns)


@tree.command(name="solar", description="Show current solar conditions")
async def slash_solar(interaction: discord.Interaction):
    await send_command_result(interaction, get_solar)


@tree.command(name="call", description="Look up a callsign in the HamQTH callbook")
async def slash_call(interaction: discord.Interaction, callsign: str):
    await send_command_result(interaction, get_calldata, callsign)


@tree.command(name="dxcc", description="Look up a callsign or entity using HamQTH data")
async def slash_dxcc(interaction: discord.Interaction, query: str):
    await send_command_result(interaction, get_dxcc, query)


@tree.command(name="muf", description="Get the MUF between two grids or callsigns")
async def slash_muf(interaction: discord.Interaction, from_locator: str, to_locator: str):
    await send_command_result(interaction, get_muf, f"{from_locator} {to_locator}")


@tree.command(name="help", description="Show DORCbot commands")
async def slash_help(interaction: discord.Interaction, command: str = ""):
    await send_command_result(interaction, get_help, command)


callsign_commands = discord.app_commands.Group(
    name="callsign", description="Register the callsign DORCbot uses for you"
)
tree.add_command(callsign_commands)


@callsign_commands.command(name="set", description="Register or update your callsign")
async def callsign_set(interaction: discord.Interaction, callsign: str):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Callsigns can only be registered inside a server.", ephemeral=True
        )
        return
    callsign = callsign.strip().upper()
    match = shared.isvalidcallformat(callsign)
    if not match or match.group(0) != callsign:
        await interaction.response.send_message(
            "Enter a valid amateur radio callsign, such as AG7SU.", ephemeral=True
        )
        return
    await asyncio.to_thread(
        callsign_store.set, interaction.guild_id, interaction.user.id, callsign
    )
    await interaction.response.send_message(
        f"Your callsign is set to **{callsign}** for this server.", ephemeral=True
    )


@callsign_commands.command(name="show", description="Show your registered callsign")
async def callsign_show(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Callsigns can only be viewed inside a server.", ephemeral=True
        )
        return
    callsign = await asyncio.to_thread(
        callsign_store.get, interaction.guild_id, interaction.user.id
    )
    if callsign:
        message = f"Your registered callsign is **{callsign}**."
    else:
        message = (
            "You don't have a registered callsign. DORCbot will use the second "
            "word of your server nickname, or set one with `/callsign set`."
        )
    await interaction.response.send_message(message, ephemeral=True)


@callsign_commands.command(name="clear", description="Remove your registered callsign")
async def callsign_clear(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Callsigns can only be cleared inside a server.", ephemeral=True
        )
        return
    removed = await asyncio.to_thread(
        callsign_store.remove, interaction.guild_id, interaction.user.id
    )
    message = (
        "Your registered callsign was cleared. DORCbot will use your nickname if it contains one."
        if removed else "You don't have a registered callsign."
    )
    await interaction.response.send_message(message, ephemeral=True)


schedule = discord.app_commands.Group(
    name="schedule",
    description="Schedule club nets and event reminders",
)
tree.add_command(schedule)


def is_server_admin(interaction):
    return interaction.guild is not None and interaction.permissions.administrator


@schedule.command(name="create", description="Schedule an event or recurring net")
@discord.app_commands.choices(
    repeat=[
        discord.app_commands.Choice(name="One time", value="once"),
        discord.app_commands.Choice(name="Weekly net", value="weekly"),
    ]
)
@discord.app_commands.describe(
    title="Reminder name",
    start="Local date/time, for example 2026-11-15 19:00",
    timezone_name="IANA timezone, for example America/Los_Angeles",
    reminder_minutes="Minutes before start (0 posts at the start)",
)
@discord.app_commands.default_permissions(administrator=True)
async def schedule_create(
    interaction: discord.Interaction,
    title: str,
    start: str,
    timezone_name: str,
    repeat: str,
    reminder_minutes: discord.app_commands.Range[int, 0, 1440] = 15,
):
    if not is_server_admin(interaction):
        await interaction.response.send_message(
            "Only server administrators can schedule reminders.", ephemeral=True
        )
        return
    try:
        title = title.strip()
        if not title:
            raise ValueError("Enter a reminder title.")
        local_start, start_utc = parse_schedule_time(start, timezone_name)
        if start_utc <= datetime.now(timezone.utc):
            raise ValueError("Choose a start time in the future.")
        reminder_utc = start_utc - timedelta(minutes=reminder_minutes)
        reminder_id = await asyncio.to_thread(
            reminders.create,
            interaction.guild_id,
            interaction.channel_id,
            title,
            local_start,
            timezone_name,
            repeat,
            reminder_utc,
            interaction.user.id,
            reminder_minutes,
        )
    except ValueError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
        return
    except Exception:
        logger.exception("Could not create scheduled reminder")
        await interaction.response.send_message(
            "Could not save that reminder. Please try again.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Scheduled **{title}** (ID `{reminder_id}`) in <#{interaction.channel_id}>. "
        f"It starts <t:{int(start_utc.timestamp())}:F>; I’ll remind this channel "
        f"{reminder_minutes} minute(s) beforehand."
    )


@schedule.command(name="list", description="List scheduled nets and events")
async def schedule_list(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Schedules are available inside the server.", ephemeral=True
        )
        return
    rows = await asyncio.to_thread(reminders.list_for_guild, interaction.guild_id)
    if not rows:
        await interaction.response.send_message("No reminders are scheduled.")
        return
    lines = []
    for row in rows[:10]:
        local_start = datetime.fromisoformat(row["local_start"])
        stamp = int(
            local_start.replace(tzinfo=ZoneInfo(row["timezone"])).timestamp()
        )
        repeat = " · weekly" if row["recurrence"] == "weekly" else ""
        lines.append(
            f"`{row['id']}` **{row['title']}**{repeat} — "
            f"<t:{stamp}:F> in <#{row['channel_id']}>"
        )
    suffix = "\nShowing the next 10 only." if len(rows) > 10 else ""
    await interaction.response.send_message("\n".join(lines) + suffix)


@schedule.command(name="cancel", description="Cancel a scheduled reminder by ID")
@discord.app_commands.default_permissions(administrator=True)
async def schedule_cancel(interaction: discord.Interaction, reminder_id: int):
    if not is_server_admin(interaction):
        await interaction.response.send_message(
            "Only server administrators can cancel reminders.", ephemeral=True
        )
        return
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Schedules are available inside the server.", ephemeral=True
        )
        return
    cancelled = await asyncio.to_thread(
        reminders.cancel, interaction.guild_id, reminder_id
    )
    await interaction.response.send_message(
        "Reminder cancelled." if cancelled else "No active reminder found with that ID.",
        ephemeral=True,
    )


@client.event
async def on_ready():
    print(f"{client.user} has connected to Discord!")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    isBang = False
    if message.content.startswith("!"):
        async with message.channel.typing():
            command = re.search(r"(^.\w+)?\s?(.*)", message.content)
            payload = Payload()
            payload.author = message.author
            func = commandmap.get(command.group(1))
            if func is None:
                payload.content = (
                    "Unsupported command. Try asking for !help instead."
                )
            else:
                try:
                    payload = await asyncio.to_thread(
                        func[0], payload, command.group(2)
                    )
                except Exception:
                    logger.exception("Prefix command %s failed", command.group(1))
                    payload = error("That lookup failed. Please try again in a moment.")
        outgoing = await message.channel.send(**payload.send())

        def wrapper(outgoing):
            def check(reaction, user):
                return reaction.message.id == outgoing.id

            return check

        check = wrapper(outgoing)

        try:
            await client.wait_for(
                "reaction_add", timeout=payload.delete_after, check=check
            )
        except asyncio.TimeoutError:
            await outgoing.delete()
            await message.delete()

    else:
        return
        # non-command branch. @Mention Chat capabilities, maybe, eventually?
        # To use this, we need to check if the bot is mentioned in the message using
        #  if client.user.mentioned_in(message)
        # payload = "Only ! commands are supported. Ask for !help instead."


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("TOKEN is required; configure dorcbot/.env or the environment")
    client.run(TOKEN)
