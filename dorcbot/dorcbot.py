import os
import discord
import re
import requests
from dotenv import load_dotenv
from tabulate import tabulate
from xml.etree import ElementTree

load_dotenv()

TOKEN = os.environ.get('TOKEN')

client = discord.Client()

codeblock = "```"


def get_spots():
    spots = requests.get('https://dorc-stats.ag7su.com/data/3').json()
    payload = "Most recently spotted DORCs:\n\n"
    tab = []
    header = ['Call', 'freq.', 'mode', 'time']
    for spot in spots:
        row = [spot['callsign'], spot['frequency'], spot['mode'], spot['time']]
        tab.append(row)
    spots = codeblock + payload + tabulate(tab, header) + codeblock
    return spots


def get_solar():
    payload = "Solar Indices:\n\n"
    solarcontent = requests.get('https://joshmathis.com/dorc/solarxml.xml')
    tree = ElementTree.fromstring(solarcontent.content).find("./solardata")
    tab = []
    # Goofy spacing in the header because I don't know how to send fixed-width messages yet.
    header = ['As of', 'A', 'K', 'SFI']
    row = [tree.find("./updated").text,
           tree.find("./aindex").text,
           tree.find("./kindex").text,
           tree.find("./solarflux").text]
    tab.append(row)
    solar = codeblock + payload + tabulate(tab, header) + codeblock
    return solar


def get_help():
    # Dynamically create help based on the defined commands (commandmap)
    payload = "Usage: "
    for key in commandmap.keys():
        command = "\n\t" + key + " -- " + commandmap.get(key)[1]
        payload += command
    return payload


# Add commands here. Format:
#    '!command': [function_to_create_final_output], "Help text"
commandmap = {
    '!spots': [get_spots, "Get the 3 most recent spots of DORC members"],
    '!solar': [get_solar, "Get solar conditions"],
    '!help': [get_help, "Get the thing you're reading now"]
}


@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    isBang = False
    if message.content.startswith('!'):
        command = re.match(r"[^\s]+", message.content).string

        func = commandmap.get(command)
        if func is None:
            payload = "Unsupported command. Try asking for !help instead."

        else:
            payload = func[0]()

        await message.channel.send(payload)

    else:
        return
        # non-command branch. @Mention Chat capabilities, maybe, eventually?
        # To use this, we need to check if the bot is mentioned in the message using
        #  if client.user.mentioned_in(message)
        # payload = "Only ! commands are supported. Ask for !help instead."

if __name__ == "__main__":
    client.run(TOKEN)
