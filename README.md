# DORCbot

DORCbot is the Digital Oddballs Radio Club's Discord bot for amateur radio
lookups and propagation information.

## Commands

Commands are available as Discord slash commands:

- `/spots` — show the five latest DORC spots
- `/solar` — show current solar conditions
- `/call callsign` — look up a callsign through QRZ
- `/dxcc query` — look up a DXCC entity through QRZ
- `/muf from_locator to_locator` — show short and long path MUF
- `/help [command]` — list commands or show command details

The legacy `!spots`, `!solar`, `!call`, `!dxcc`, `!muf`, and `!help` commands
remain available. Slash commands work without privileged gateway intents. To
use prefix commands, set `ENABLE_PREFIX_COMMANDS=true` and enable **Message
Content Intent** for the bot in the Discord Developer Portal.

## Configure Discord

Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
When generating its invite URL, include the `bot` and `applications.commands`
scopes. The bot needs permission to view channels and send messages. Enable
Message Content Intent in the Bot settings only if you want to keep using the
legacy `!` commands.

Slash commands are registered globally at startup. Discord may take a little
while to display newly registered global commands.

## Run with Docker Compose

Copy `dorcbot/.env-template` to `dorcbot/.env`, then fill in the bot token and
optional QRZ credentials:

```sh
cp dorcbot/.env-template dorcbot/.env
# edit dorcbot/.env
docker compose up -d --build
```

The Compose service passes the values into the container as environment
variables. The container runs as an unprivileged user and restarts unless
stopped.

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

QRZ lookups require an XML subscription. Without QRZ credentials, `/call` uses
the bundled sample response; `/dxcc` and callsign-based `/muf` lookups require
credentials. Configure `QRZ_API_USER` and `QRZ_API_PASS` in the environment or
in `dorcbot/.env`.

## Development

Install runtime dependencies with `python -m pip install -r dorcbot/requirements.txt`.
Run the unit suite with `python -m unittest`.
