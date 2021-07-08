import os
import discord
import re
import requests
from dotenv import load_dotenv
from tabulate import tabulate
from xml.etree import ElementTree
import asyncio
import shared
import kc2g
import xmltodict

load_dotenv()

TOKEN = os.environ.get('TOKEN')
QRZ_API_USER = os.environ.get('QRZ_API_USER')
QRZ_API_PASS = os.environ.get('QRZ_API_PASS')
QRZCALLSIGNSAMPLE = "qrzcallsignsample.xml"

cannedQRZ = (QRZ_API_USER is None)

client = discord.Client()

# Command map & help columns
COMMANDMAP_FUNC = 0
COMMANDMAP_SHORT_HELP = 1
COMMANDMAP_LONG_HELP_FUNC = 2


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


def error(description):
    payload = Payload(fmt='')
    payload.embed = discord.Embed(color=0xFF5733, title='Error:')
    payload.embed.description = description
    payload.embed.set_thumbnail(url='https://c.tenor.com/OxvVRFnPZO8AAAAM/error-the-simpsons.gif')

    return payload

def usercall(user):
    call = user.display_name.split()
    if len(call) > 1 and re.search('[a-zA-Z0-9]{1,3}[0123456789][a-zA-Z0-9]{0,3}[a-zA-Z]', call[1]):
        return calldata(call[1]) 
    else:
        return None


def calldata(callsign):
    if cannedQRZ:
        with open(QRZCALLSIGNSAMPLE) as fd:
            calldata = xmltodict.parse(fd.read())["Callsign"]
    else:
        callsign = callsign.split(';')[0]
        pref = '{http://xmldata.qrz.com}'
        login = requests.get(
            f'https://xmldata.qrz.com/xml/current/?username={QRZ_API_USER};password={QRZ_API_PASS};agent=q5.0')
        key = ElementTree.fromstring(login.content)[0][0].text
        resp = ElementTree.fromstring(
            requests.get(f'https://xmldata.qrz.com/xml/current/?s={key};callsign={callsign}').content)
        data = resp.find(pref + 'Callsign')
        if data:
            calldata = {x.tag.split('}')[1]: x.text for x in data}
        else:
            return None

    return calldata


def dxcc(query):
    query = query.split(';')[0].upper()  # allow one parameter only
    pref = '{http://xmldata.qrz.com}'
    login = requests.get(
        f'https://xmldata.qrz.com/xml/current/?username={QRZ_API_USER};password={QRZ_API_PASS};agent=q5.0')

    key = ElementTree.fromstring(login.content)[0][0].text
    resp = ElementTree.fromstring(requests.get(f'https://xmldata.qrz.com/xml/current/?s={key};dxcc={query}').content)
    data = resp.find(pref + 'DXCC')
    if data:
        dxcc = {x.tag.split('}')[1]: x.text for x in data}
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
        payload = error(f"API returned no result for dxcc matching: {query.upper()}")

    return payload


def get_calldata(payload, callsign, *args):
    data = calldata(callsign.split()[0])
    if data:
        payload.content = f"Data for {data['call']}\n\n"
        payload.content += f"Callsign: {data['call']} [ Aliases: {data.get('aliases')} ]\n"
        payload.content += f"Name: {data['fname']} {data['name']}\n"
        payload.content += f"Country: {data['country']}\n"
        payload.content += f"State: {data.get('state')}\n"
        payload.content += f"Grid: {data['grid']}"
    else:
        payload = error("Check callsign")

    return payload


def get_spots(payload, *args):
    spots = requests.get('https://dorc-stats.ag7su.com/data/5').json()
    payload.content = "Most recently spotted DORCs:\n\n"
    tab = []
    header = ['Call', 'freq.', 'mode', 'time']
    if spots[0].get('callsign'):
        for spot in spots:
            row = [spot['callsign'], spot['frequency'], spot['mode'], spot['time']]
            tab.append(row)
        payload.content = payload.content + tabulate(tab, header)
    else:
        payload = error("API returned no records")

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


def get_mof(payload, query, *args):
    query = query.split()
    if len(query) == 2:
        loc_from = query[0]
        loc_to = query[1]
    else:
        user_call = usercall(payload.author)
        if len(query) == 1 and user_call: 
            loc_from = user_call['grid'] 
            loc_to = query[0]
        else:
            payload = error("Invalid input. Try !help mof for usage")
            return payload
    # validate griddiness. If no gridditude, assume it's a callsign
    #   If no grid is available, it will come back blank and fail the check below.
    if not shared.isvalidgrid(loc_from):
        loc_from = callsign_grid(loc_from)

    if not shared.isvalidgrid(loc_to):
        loc_to = callsign_grid(loc_to)

    if shared.isvalidgrid(loc_from) and shared.isvalidgrid(loc_to):
        payload.content = f"MOF from {loc_from.upper()} to {loc_to.upper()}:\n\n"
        mof = kc2g.mof(loc_from, loc_to)
        tab = []
        header = ['MOF Short Path', 'MOF Long Path']
        row = [mof['mof_sp'],
               mof['mof_lp']]
        tab.append(row)
        payload.content = payload.content + tabulate(tab, header)
    else:
        payload = error("Invalid input. Enter a valid grid or callsign")
    return payload


def mof_usage():
    return """
    Get MOF (courtesy of KC2G / prop.kc2g.org)
    
    Returns the latest Maximum Observed Frequency between two grid squares via long & short paths.
    
    If a callsign is used for one or both locators, bot will attempt to find the operator's home grid via QRZ lookup. 

    If your server display name is in the exact format "Name Callsign" i.e. "Tyler AG7SU" or "displayname AG7SU"
    you may omit a starting grid to use the grid associated with your callsign on QRZ. e.g. `!mof W1AW`
    
    """


def callsign_grid(callsign):
    callsigndata = calldata(callsign)
    if callsigndata and 'grid' in callsigndata.keys() and len(callsigndata['grid']) > 0:
        return callsigndata['grid']
    else:
        return None


def get_help(payload, query, *args):
    # Dynamically create help based on the defined commands (commandmap)
    query = query.split()
    payload.content = "Usage: "
    if len(query) == 0:
        for key in commandmap.keys():
            command = "\n\t" + key + " -- " + commandmap.get(key)[COMMANDMAP_SHORT_HELP]
            payload.content += command
    else:
        # Help on a specific command
        # Show regular help if advanced is not available
        if query[0].startswith("!"):
            commandname = query[0]
        else:
            commandname = "!" + query[0]
        if commandname in commandmap.keys():
            command = "\n\t" + query[0] + " -- " + commandmap.get(commandname)[COMMANDMAP_SHORT_HELP]
            payload.content += command
            if len(commandmap.get(commandname)) > COMMANDMAP_LONG_HELP_FUNC:
                payload.content += "\n\t" + commandmap.get(commandname)[COMMANDMAP_LONG_HELP_FUNC]()
        else:
            payload.content = f"Command {commandname} not found. Try !help instead."
    return payload


# Add commands here. Format:
#    '!command': [function_to_create_final_output], "Help text", detailed_usage_function_name
commandmap = {
    '!spots': [get_spots, "Get the 5 most recent spots of DORC members"],
    '!solar': [get_solar, "Get solar conditions"],
    '!call': [get_calldata, "Get callsign info '!call <callsign>'"],
    '!dxcc': [get_dxcc, "Get dxcc info '!dxcc <query>'"],
    '!mof': [get_mof, "Get maximum observed frequency between "
                      "grid squares or callsigns '!mof <from_locator> <to_locator>'", mof_usage],
    '!help': [get_help, "Get the thing you're reading now. Use !help <command> for detailed help, if available."]
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
            payload.author = message.author
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
