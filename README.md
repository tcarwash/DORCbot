# DORCbot

## What is DORCbot?
This is the very beginnings of a bot for the Digital Oddballs Radio Club discord server

## Setup
### Before you start
To run DORCbot you will need to have completed all the steps to create an app and bot in the Discord Developer Portal. Instructions can be found [here](https://discordpy.readthedocs.io/en/stable/discord.html)

### Docker and Docker-Compose
1. Create a file `dorcbot/.env` with the entry `TOKEN={Discord Bot Token}`
2. run `docker-compose build`
3. start container with `docker-compose up` or `docker-compose up -d` for detached

### Python, No Docker
1. Create a file `.env` with the entry `TOKEN={Discord Bot Token}`
2. Run `python dorcbot.py`

## Next Steps
More features!
