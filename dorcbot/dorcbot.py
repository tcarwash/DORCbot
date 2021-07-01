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


class Payload:
    def __init__(self, fmt='code', content='', delete_after=120):
        self.fmt = fmt
        self.content = content
        self.arg_dict = {'content': self.content, 
                        'delete_after': delete_after}

    def block(self, content):
        return f"```{content}```"

    def send(self):
        if self.fmt == 'code':
            self.content = self.block(self.content)
            self.arg_dict['content'] = self.content

        return self.arg_dict
                

def get_spots(payload):
    spots = requests.get('https://dorc-stats.ag7su.com/data/3').json()
    payload.content = "Most recently spotted DORCs:\n\n"
    tab = []
    header = ['Call', 'freq.', 'mode', 'time']
    for spot in spots:
        row = [spot['callsign'], spot['frequency'], spot['mode'], spot['time']]
        tab.append(row)
    payload.content = payload.content + tabulate(tab, header)
    return payload


def get_solar(payload):
    payload.content = "Solar Indices:\n\n"
    solarcontent = requests.get('https://joshmathis.com/dorc/solarxml.xml')
    tree = ElementTree.fromstring(solarcontent.content).find("./solardata")
    tab = []
    header = ['As of', 'A', 'K', 'SFI']
    row = [tree.find("./updated").text,
           tree.find("./aindex").text,
           tree.find("./kindex").text,
           tree.find("./solarflux").text]
    tab.append(row)
    payload.content = payload.content + tabulate(tab, header)
    return payload 


def get_help(payload):
    # Dynamically create help based on the defined commands (commandmap)
    payload.content = "Usage: "
    for key in commandmap.keys():
        command = "\n\t" + key + " -- " + commandmap.get(key)[1]
        payload.content += command
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
        payload = Payload()
        func = commandmap.get(command)
        if func is None:
            payload.content = "Unsupported command. Try asking for !help instead."

        else:
            payload = func[0](payload)

        await message.channel.send(**payload.send())

    else:
        return
        # non-command branch. @Mention Chat capabilities, maybe, eventually?
        # To use this, we need to check if the bot is mentioned in the message using
        #  if client.user.mentioned_in(message)
        # payload = "Only ! commands are supported. Ask for !help instead."

if __name__ == "__main__":
    client.run(TOKEN)
