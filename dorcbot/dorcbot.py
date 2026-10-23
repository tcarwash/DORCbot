import os
import discord
import re
import requests
from dotenv import load_dotenv
from tabulate import tabulate
from xml.etree import ElementTree
import asyncio
import logging
from pathlib import Path
from . import kc2g, shared
import xmltodict

load_dotenv(Path(__file__).with_name(".env"))
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dorcbot")

TOKEN = os.environ.get("TOKEN")
QRZ_API_USER = os.environ.get("QRZ_API_USER")
QRZ_API_PASS = os.environ.get("QRZ_API_PASS")
QRZCALLSIGNSAMPLE = Path(__file__).with_name("qrzcallsignsample.xml")

cannedQRZ = not QRZ_API_USER or not QRZ_API_PASS

intents = discord.Intents.default()
# Enable the privileged gateway intent only when legacy prefix commands are
# requested. Slash commands work without Message Content access.
intents.message_content = os.environ.get("ENABLE_PREFIX_COMMANDS", "false").lower() in {
    "1", "true", "yes", "on"
}
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


@client.event
async def setup_hook():
    await tree.sync()

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
    call = user.display_name.split()
    if len(call) > 1 and shared.isvalidcallformat(call[1]):
        return calldata(call[1])
    else:
        return None


def calldata(callsign):
    if cannedQRZ:
        with open(QRZCALLSIGNSAMPLE) as fd:
            calldata = xmltodict.parse(fd.read())["Callsign"]
    else:
        callsign = callsign.split(";")[0]
        pref = "{http://xmldata.qrz.com}"
        login = requests.get(
            "https://xmldata.qrz.com/xml/current/",
            params={"username": QRZ_API_USER, "password": QRZ_API_PASS, "agent": "DORCbot"},
            timeout=15,
        )
        key = ElementTree.fromstring(login.content)[0][0].text
        resp = ElementTree.fromstring(
            requests.get(
                "https://xmldata.qrz.com/xml/current/",
                params={"s": key, "callsign": callsign},
                timeout=15,
            ).content
        )
        data = resp.find(pref + "Callsign")
        if data:
            calldata = {x.tag.split("}")[1]: x.text for x in data}
        else:
            return None

    return calldata


def dxcc(query):
    if cannedQRZ:
        return None
    query = query.split(";")[0].upper()  # allow one parameter only
    pref = "{http://xmldata.qrz.com}"
    login = requests.get(
        "https://xmldata.qrz.com/xml/current/",
        params={"username": QRZ_API_USER, "password": QRZ_API_PASS, "agent": "DORCbot"},
        timeout=15,
    )

    key = ElementTree.fromstring(login.content)[0][0].text
    resp = ElementTree.fromstring(
        requests.get(
            "https://xmldata.qrz.com/xml/current/",
            params={"s": key, "dxcc": query},
            timeout=15,
        ).content
    )
    data = resp.find(pref + "DXCC")
    if data:
        dxcc = {x.tag.split("}")[1]: x.text for x in data}
    else:

        return None

    return dxcc


def get_dxcc(payload, query, *args):
    data = dxcc(query.split()[0])
    if data:
        payload.content = f"DXCC Data for {query.upper()}\n\n"
        payload.content += f"DXCC Number: {data.get('dxcc')}\n"
        payload.content += f"Country: {data.get('name')}\n"
        payload.content += f"CC: {data.get('cc')}\n"
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
    data = calldata(callsign.split()[0])
    if data:
        payload.content = f"Data for {data['call']}\n\n"
        payload.content += (
            f"Callsign: {data['call']} [ Aliases: {data.get('aliases')} ]\n"
        )
        payload.content += f"Name: {data['fname']} {data['name']}\n"
        payload.content += f"Country: {data['country']}\n"
        payload.content += f"State: {data.get('state')}\n"
        payload.content += f"Grid: {data['grid']}"
    else:
        payload = error("Check callsign")

    return payload


def get_spots(payload, *args):
    spots = requests.get("https://dorc-stats.ag7su.com/data/5", timeout=15).json()
    payload.content = "Most recently spotted DORCs:\n\n"
    tab = []
    header = ["Call", "freq.", "mode", "time"]
    if spots[0].get("callsign"):
        for spot in spots:
            row = [
                spot["callsign"],
                spot["frequency"],
                spot["mode"],
                spot["time"],
            ]
            tab.append(row)
        payload.content = payload.content + tabulate(tab, header)
    else:
        payload = error("API returned no records")

    return payload


def get_solar(payload, *args):
    payload.content = "Solar Indices (courtesy of hamqsl.com):\n\n"
    solarcontent = requests.get("https://joshmathis.com/dorc/solarxml.xml", timeout=15)
    tree = ElementTree.fromstring(solarcontent.content).find("./solardata")
    tab = []
    header = ["As of", "A", "K", "SFI"]
    row = [
        tree.find("./updated").text,
        tree.find("./aindex").text,
        tree.find("./kindex").text,
        tree.find("./solarflux").text,
    ]
    tab.append(row)
    payload.content = payload.content + tabulate(tab, header)

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

    If a callsign is used for one or both locators, bot will attempt to find the operator's home grid via QRZ lookup.

    If your server display name is in the exact format "Name Callsign" i.e. "Tyler AG7SU" or "displayname AG7SU"
    you may omit a starting grid to use the grid associated with your callsign on QRZ. e.g. `!muf W1AW`

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
    "!spots": [get_spots, "Get the 5 most recent spots of DORC members"],
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


async def send_command_result(interaction, function, query=""):
    """Run a blocking data lookup away from Discord's event loop."""
    payload = Payload()
    payload.author = interaction.user
    try:
        payload = await asyncio.to_thread(function, payload, query)
        await interaction.response.send_message(**payload.send())
    except Exception:
        # Keep service details and credentials out of public Discord messages.
        logger.exception("Slash command %s failed", function.__name__)
        message = "That lookup failed. Please try again in a moment."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


@tree.command(name="spots", description="Show the five latest DORC spots")
async def slash_spots(interaction: discord.Interaction):
    await send_command_result(interaction, get_spots)


@tree.command(name="solar", description="Show current solar conditions")
async def slash_solar(interaction: discord.Interaction):
    await send_command_result(interaction, get_solar)


@tree.command(name="call", description="Look up a callsign on QRZ")
async def slash_call(interaction: discord.Interaction, callsign: str):
    await send_command_result(interaction, get_calldata, callsign)


@tree.command(name="dxcc", description="Look up a DXCC entity on QRZ")
async def slash_dxcc(interaction: discord.Interaction, query: str):
    await send_command_result(interaction, get_dxcc, query)


@tree.command(name="muf", description="Get the MUF between two grids or callsigns")
async def slash_muf(interaction: discord.Interaction, from_locator: str, to_locator: str):
    await send_command_result(interaction, get_muf, f"{from_locator} {to_locator}")


@tree.command(name="help", description="Show DORCbot commands")
async def slash_help(interaction: discord.Interaction, command: str = ""):
    await send_command_result(interaction, get_help, command)


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
