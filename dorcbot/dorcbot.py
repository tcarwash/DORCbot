import os
import discord
from dotenv import load_dotenv
from tabulate import tabulate
import requests

load_dotenv()

TOKEN = os.environ.get('TOKEN')

client = discord.Client()

def get_spots():
    spots = requests.get('https://dorc-stats.ag7su.com/data/3').json()
    payload = "Most recently spotted DORCs:\n\n"
    tab = []
    header = ['Call', 'freq.', 'mode', 'time']
    for spot in spots:
        row = [spot['callsign'], spot['frequency'], spot['mode'], spot['time']]
        tab.append(row)
    spots = payload + tabulate(tab, header)
    return spots

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')

@client.event
async def on_message(message):
    if message.content.startswith('!spots'):
        payload = get_spots()
        await message.channel.send(payload)

    if message.content.startswith('!help'):
        payload ="""
        Usage:
            !help --  Display this message 
            !spots --  Get the 3 most recent spots of DORC members

        """
        await message.channel.send(payload)

client.run(TOKEN)
