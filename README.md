# DORCbot

## What is DORCbot?
This is the repository for the Digital Oddballs Radio Club's Discord chat bot. The bot provides amateur related information sourced from multiple sources.

### Features
  - !spots -- Get the 5 most recent spots of DORC members
  - !solar -- Get solar conditions
  - !call -- Get callsign info '!call '
  - !dxcc -- Get dxcc info '!dxcc '
  - !mof -- Get maximum observed frequency between grid squares or callsigns '!mof <from_locator> <to_locator>'
  - !help -- Get the thing you're reading now. Use !help

## Setup
### Before you start
To run DORCbot you will need to have completed all the steps to create an app and bot in the Discord Developer Portal. Instructions can be found [here](https://discordpy.readthedocs.io/en/stable/discord.html)

### Docker and Docker-Compose
1. Create a file `dorcbot/.env` example:
```
TOKEN={Discord Bot Token}
QRZ_API_USER={QRZ api username}
PRZ_API_PASS={QRZ api password}

```
2. run `docker-compose build`
3. start container with `docker-compose up` or `docker-compose up -d` for detached

### Python, No Docker
1. Create a file `dorcbot/.env` as above
2. Install dependencies `python -m pip install -r dorcbot/requirements.txt`
2. Run `python dorcbot.py`

## Next Steps
More features!
