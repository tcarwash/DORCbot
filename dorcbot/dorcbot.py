import os
import discord
import re
import requests
from dotenv import load_dotenv
from tabulate import tabulate
from xml.etree import ElementTree
import asyncio

load_dotenv()

TOKEN = os.environ.get('TOKEN')
QRZ_API_USER = os.environ.get('QRZ_API_USER')
QRZ_API_PASS = os.environ.get('QRZ_API_PASS')

client = discord.Client()


class Payload:
    def __init__(self, fmt='codeblock', content='', delete_after=60):
        self.fmt = fmt
        self.content = content
        self.delete_after = delete_after


    def to_dict(self):
        # List of attributes not to send to Discord
        keep = ['content', 'tts', 
                'embed', 'file', 'files', 'nonce', 
                'allowed_mentions', 'reference', 'mention_author']

        arg_dict = {k: self.__dict__[k] for k in keep if k in self.__dict__} 

        return arg_dict


    def format_block(self):
        if self.fmt == 'codeblock':
            self.content = f"```{self.content}```"

        return True


    def send(self):
        self.format_block()
        arg_dict = self.to_dict()

        return arg_dict

def calldata(callsign):
    pref = '{http://xmldata.qrz.com}'
    login = requests.get(f'https://xmldata.qrz.com/xml/current/?username={QRZ_API_USER};password={QRZ_API_PASS};agent=q5.0')
    key = ElementTree.fromstring(login.content)[0][0].text
    resp = ElementTree.fromstring(requests.get(f'https://xmldata.qrz.com/xml/current/?s={key};callsign={callsign}').content)
    data = resp.find(pref + 'Callsign')
    if data:
        calldata = {'callsign': data.find(pref + 'call').text,
                    'fname': data.find(pref + 'fname').text,
                    'lname': data.find(pref + 'name').text,
                    'country': data.find(pref + 'country').text,
                    'grid': data.find(pref + 'grid').text,
                    }
    else:
        calldata = {"error": "Invalid"}

    return calldata 

def get_calldata(payload, callsign, *args):
    data = calldata(callsign.split()[0])
    if 'error' in data:
        payload.content = "Check callsign"
        return payload
    else:
        payload.content = f"Data for {data['callsign']}\n\n"
        payload.content += f"Callsign: {data['callsign']}\n"
        payload.content += f"Name: {data['fname']} {data['lname']}\n"
        payload.content += f"Country: {data['country']}\n"
        payload.content += f"Grid: {data['grid']}"
    return payload

def get_spots(payload, *args):
    spots = requests.get('https://dorc-stats.ag7su.com/data/5').json()
    payload.content = "Most recently spotted DORCs:\n\n"
    tab = []
    header = ['Call', 'freq.', 'mode', 'time']
    for spot in spots:
        row = [spot['callsign'], spot['frequency'], spot['mode'], spot['time']]
        tab.append(row)
    payload.content = payload.content + tabulate(tab, header)
    return payload


def get_solar(payload, *args):
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


def get_help(payload, *args):
    # Dynamically create help based on the defined commands (commandmap)
    payload.content = "Usage: "
    for key in commandmap.keys():
        command = "\n\t" + key + " -- " + commandmap.get(key)[1]
        payload.content += command
    return payload 


# Add commands here. Format:
#    '!command': [function_to_create_final_output], "Help text"
commandmap = {
    '!spots': [get_spots, "Get the 5 most recent spots of DORC members"],
    '!solar': [get_solar, "Get solar conditions"],
    '!call': [get_calldata, "Get callsign info '!Call <callsign>'"],
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
        async with message.channel.typing():
            command = re.search(r"(^.\w+)?\s?(.*)", message.content)
            payload = Payload()
            func = commandmap.get(command.group(1))
            if func is None:
                payload.content = "Unsupported command. Try asking for !help instead."
            else:
                payload = func[0](payload, command.group(2))
        outgoing = await message.channel.send(**payload.send())

        def wrapper(outgoing):
            def check(reaction, user):
                return reaction.message.id == outgoing.id
            return check

        check = wrapper(outgoing)

        try:
            await client.wait_for('reaction_add', timeout=payload.delete_after, check=check)
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
    client.run(TOKEN)
#    calldata(input('Call?'))
