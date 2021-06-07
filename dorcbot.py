import os
import discord
from dotenv import load_dotenv
import requests

load_dotenv()

TOKEN = os.environ.get('TOKEN')

client = discord.Client()

def get_spots():
    spots = requests.get('https://dorc-stats.ag7su.com/data/3').json()
    return spots

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')

@client.event
async def on_message(message):
    
    if message.content.startswith('!spots'):
        spots = get_spots()
        payload = "Most recently spotted DORCs: \n \n|-- call --|-- freq. --|-- mode --|-- time --|\n"
        for spot in spots:
            payload = payload + "|{} |{} |{} |{} |\n".format(spot['callsign'], 
                    spot['frequency'], 
                    spot['mode'], 
                    spot['time']
                    )
        await message.channel.send(payload)

client.run(TOKEN)
