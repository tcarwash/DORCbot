# DORCbot

DORCbot is the Digital Oddballs Radio Club's Discord bot for amateur radio
lookups and propagation information.

## Commands

Commands are available as Discord slash commands:

- `/spots` — show recent DX cluster spots for configured DORC callsigns
- `/solar` — show solar radio flux and planetary K index from NOAA
- `/call callsign` — look up a callsign through HamQTH
- `/dxcc query` — look up a callsign or DXCC entity through HamQTH data
- `/muf from_locator to_locator` — show short and long path MUF
- `/help [command]` — list commands or show command details
- `/callsign set|show|clear` — register or manage your callsign for this server
- `/schedule create` — admins schedule a one time event or weekly net
- `/schedule list` — show scheduled reminders
- `/schedule cancel` — admins cancel a reminder by ID

Schedule times use local ISO format, such as `2026-11-15 19:00`, plus an IANA
timezone such as `America/Los_Angeles`. Choose a weekly repeat for a recurring
net. The default reminder posts 15 minutes before start; admins can choose a
different lead time or `0` to post at the start. Reminders are posted to the
channel where they were created. The Compose named volume keeps schedules
across container rebuilds and restarts.

KISSChat can forward radio messages that mention `@dorcbot` to a Discord text
channel with the same name as the KISSChat channel. Set
`KISSCHAT_BRIDGE_TOKEN` to a long random secret in `dorcbot/.env`, keep the
bridge port (`8765` by default) reachable only from trusted KISSChat stations,
and configure each station with `KISSCHAT_DORCBOT_URL` and the same
`KISSCHAT_DORCBOT_TOKEN`. DORCbot records delivered `(origin, sequence)` IDs
in its persistent data volume, so relays receiving the same radio message do
not post it twice. KISSChat sends its mention receipt only after DORCbot
confirms the Discord post.

The legacy `!spots`, `!solar`, `!call`, `!dxcc`, `!muf`, and `!help` commands
remain available. Most slash commands work without privileged gateway intents;
`/spots` nickname scanning needs Guild Members Intent. To use prefix commands,
set `ENABLE_PREFIX_COMMANDS=true` and enable **Message Content Intent** for the
bot in the Discord Developer Portal.

`/spots` reads callsigns from the second word of each member's server nickname,
using the same convention as `/muf` (for example, `Tyler AG7SU`). A member's
`/callsign set` registration takes precedence over their nickname;
`/callsign clear` returns to nickname detection. Enable **Guild Members
Intent** in the Developer Portal for nickname scanning. `DORC_CALLSIGNS` can still supply extra
callsigns that are not tied to a server member.

Slash commands sync globally by default, and Discord may take time to show
global commands. For immediate availability in one server, set
`DISCORD_GUILD_ID` to that server's ID; the bot will sync commands to that
server at startup. The bot also logs the number of commands synced.

## Configure Discord

Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
When generating its invite URL, include the `bot` and `applications.commands`
scopes. The bot needs permission to view channels, send messages, and embed
links (KISSChat posts arrive as embeds). Enable **Guild Members Intent** in the
Bot settings for `/spots` nickname scanning. Enable **Message Content Intent**
only if you want to keep using the legacy `!` commands.

Slash commands are registered globally at startup. Discord may take a little
while to display newly registered global commands.

## Run with Docker Compose

Copy `dorcbot/.env-template` to `dorcbot/.env`, then set the bot token and the
club's comma-separated callsigns. HamQTH credentials are optional and only
needed for international callbook lookups:

```sh
cp dorcbot/.env-template dorcbot/.env
# edit dorcbot/.env
docker compose up -d --build
```

The Compose service passes the values into the container as environment
variables. The container runs as an unprivileged user and restarts unless
stopped. Keep the `dorcbot_data` volume when recreating the service; it contains
the reminder schedule database.

## Run with Python

Python 3.12 or newer is recommended.

```sh
cp dorcbot/.env-template dorcbot/.env
# edit dorcbot/.env
python -m venv .venv
. .venv/bin/activate
python -m pip install -r dorcbot/requirements.txt
python -m dorcbot.dorcbot
```

`/spots` uses HamQTH's public DX cluster endpoint. Set `DORC_CALLSIGNS` to a
comma-separated list of up to 30 member callsigns, for example
`DORC_CALLSIGNS=AG7SU,W1AW`. HamQTH asks clients not to poll this endpoint more
often than every 15 seconds; DORCbot caches results for one minute. `/solar`
uses NOAA SWPC's public JSON feeds. `/dxcc` uses HamQTH's no-login DXCC data.

International callbook profiles and callsign-based `/muf` lookups use
HamQTH's free API account. Create an account and set `HAMQTH_CALLSIGN` and
`HAMQTH_PASSWORD`; DORCbot keeps the API token in memory and sends the password
only to HamQTH over HTTPS. Spot, solar, DXCC, and grid-to-grid MUF lookups do
not need these credentials. HamQTH requests that applications credit its data;
DORCbot labels HamQTH in `/spots` and in this setup guide.

## Development

Install runtime dependencies with `python -m pip install -r dorcbot/requirements.txt`.
Run the unit suite with `python -m unittest`.
