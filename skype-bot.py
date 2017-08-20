#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2017 Infi


import re
import os
import sys
import discord
import asyncio
import logging
import datetime
from skpy import Skype
from importlib import reload
from argparse import ArgumentParser
from configparser import ConfigParser

__version__ = "0.1.0-Alpha"
PROG_NAME = "skype-bot"

if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)


class ImproperlyConfigured(Exception):
    pass


def parse_args():
    version = f"{PROG_NAME}-{__version__}"
    p = ArgumentParser(prog=PROG_NAME)
    p.add_argument("--version", action="version", version=version)
    p.add_argument("--config")

    return p.parse_args()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.path.expanduser("~")
DEFAULT_CONFIG_PATHS = [
    os.path.join(HOME_DIR, ".skype-bot.ini"),
    os.path.join(BASE_DIR, "feed2discord.local.ini"),
    os.path.join("feed2discord.local.ini"),
    os.path.join("/etc/skype-bot.ini"),
    os.path.join(BASE_DIR, "skype-bot.ini"),
    os.path.join("skype-bot.ini"),
]


def get_config():
    args = parse_args()
    config = ConfigParser()
    if args.config:
        config.read(args.config)
    else:
        for path in DEFAULT_CONFIG_PATHS:
            if os.path.isfile(path):
                config.read(path)
                break
        else:
            raise ImproperlyConfigured("No configuration file found.")

    debug = config["MAIN"].getint("debug", 0)

    if debug:
        os.environ["PYTHONASYNCIODEBUG"] = "1"
        # The AIO modules need to be reloaded because of the new env var
        reload(asyncio)
        reload(discord)

    if debug >= 3:
        log_level = logging.DEBUG
    elif debug >= 2:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(level=log_level)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)

    return config, logger


def get_channel(config):
    ch = {}
    for key, channel_id in config["DISCORD_CHANNELS"].items():
        ch[channel_id] = [sk.chats[f"{config['SKYPE_CHANNELS'][key]}"], discord.Object(id=f"{channel_id}")]
    logger.info(f"Generated channel list.")

    return ch

config, logger = get_config()

# Make main config area global, since used everywhere/anywhere
MAIN = config['MAIN']

# global discord client object
client = discord.Client()

# precompile regex for global use
rex = re.compile("<:(\w+):(\d+)>")
rex_mention = re.compile("<@!?(\d+)>")
rex_mention_role = re.compile("<@&(\d+)>")
rex_mention_channel = re.compile("<#(\d+)>")
rex_username = re.compile("@(\w+)")

# get skype connection
sk = Skype(MAIN.get("skype_email"), MAIN.get("skype_password"))

# global variables
date_format = "%a %d %b %H:%M:%S"
discord_url = "https://cdn.discordapp.com/emojis/"
ch = get_channel(config)
skype_content_list = {}
discord_content_list = {}

# global variables that not can be set directly.
def set_global_variables():
    global discord_id, skype_id
    discord_id = [str(client.user.id)]
    skype_id = [str(sk.user.id)]
    for x in config["FORBIDDEN_DISCORD"].values():
        discord_id.append(str(x))
    for x in config["FORBIDDEN_SKYPE"].values():
        skype_id.append(str(x))
    logger.info(f"Forbidden Skype:\n{skype_id}\nForbidden Discord:\n{discord_id}")

# From skpy
def markup(x):
    if x.content is None:
        return None
    text = re.sub(r"<e.*?/>", "", x.content)
    text = re.sub(r"</?b.*?>", "*", text)
    text = re.sub(r"</?i.*?>", "_", text)
    text = re.sub(r"</?s.*?>", "~", text)
    text = re.sub(r"</?pre.*?>", "{code}", text)
    text = re.sub(r"""<a.*?href="(.*?)">.*?</a>""", r"\1", text)
    text = re.sub(r"""<at.*?id="8:(.*?)">.*?</at>""", r"@\1", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&") \
               .replace("&quot;", "\"").replace("&apos;", "'")
    return text


def edit_skype_message(message):
    right_mes = ""
    # Search and replace skype-quotes for discord styles quotes
    if "<quote" in message.content:
        mes = message.content.split(">")
        for index, mes_split_item in enumerate(mes):
            if "</legacyquote" in mes_split_item:
                if not "&lt;&lt;&lt;" in mes_split_item:
                    right_mes += f">{mes_split_item[:-13]}\n"
            if "<legacyquote" in mes_split_item:
                if len(mes_split_item) != 12:
                    right_mes += f" {mes_split_item[:-12]}\n\n\n"
        mes = message.content.split("</quote>")[-1]
        message.content = right_mes + mes

    skype_con = markup(message)
    skype_con = skype_con.split(" ")
    user_id = []
    # Search and replace discord mention with the discord code for mentions
    for index, sky_mes in enumerate(skype_con):
        username = re.match(rex_username, sky_mes)
        if username:
            for user in client.get_all_members():
                y = str(username.group(1))
                if re.search(y, user.name) or (user.nick and re.search(y, user.nick)):
                    user_id.append(user.id)
            user_names = ""
            if user_id:
                for us_id in user_id:
                    user_names += f"<@{us_id}> "
            skype_con[index] = user_names

    message_con = " ".join(skype_con)
    message_con = message_con.replace("{code}", "```")
    message_con = message_con.replace("&lt;&lt;&lt;", "")
    return message_con

# Search for skypes messages with specifed content
def inspect_skype_content(message):
    if "<URIObject" in message.content:
        mes = message.content.split("url_thumbnail=\"")[1]
        mes = mes.split("\"")[0]
        return [f"**{message.user.name}** sended a file ... here the preview {mes}", message.clientId, False]
    elif "<addmember" in message.content:
        return [f"**{message.user.name}** joined the chat in skype!", message.clientId, False]
    elif "<delete" in message.content:
        mes = message.content.split("<target>")[1]
        mes = mes.split("</target>")[0]
        mes = mes[2:]
        return [f"**{mes}** was removed from the chat in skype!", message.clientId, False]
    else:
        message_con = edit_skype_message(message)
        return [f"**{message.user.name}**: {message_con}", message.clientId, False]

# if message.content, the discord messages will be edited
# else the discord messages will be deleted
def inspect_skype_content_edit(message):
    if message.content:
        message_con = edit_skype_message(message)
        message_con = message_con.replace("Edited previous message:", "")
        return[f"**{message.user.name}**: {message_con}", message.clientId, True, False]
    else:
        return ["", message.clientId, True, True]

# Get all skype messages and process it
# Endless loop with a 1s sleep for API behaviors
async def skype_loop():
    logger.warning("Start skype_loop.")
    while client.is_logged_in:
        await asyncio.sleep(1)
        for chat_instance in ch.values():
            message_list = []
            time_now = datetime.datetime.now() - datetime.timedelta(hours=2, minutes=1)
            mes = chat_instance[0].getMsgs()
            for message_sky in mes:
                if not message_sky.user.id in skype_id:
                    if message_sky.time > time_now:
                        if not str(message_sky.clientId) in skype_content_list.keys():
                            skype_content_list[message_sky.clientId] = {
                                "time": message_sky.time,
                                "discord_id": "",
                            }
                            message_list.append(inspect_skype_content(message_sky))
                        else:
                            message_list.append(inspect_skype_content_edit(message_sky))
                    else:
                        break

            # Discord messages lenght is limited to 2000 chars.
            # If len > 1800 chars the messages will get truncated.
            for content in message_list[::-1]:
                if len(content[0]) > 1800:
                    content[0] = content[0][:1800] + "... Message truncated"
                if not content[2]:
                    message = await client.send_message(chat_instance[1], content[0])
                    try:
                        skype_content_list[str(content[1])]["discord_id"] = f"{message.id}"
                    except KeyError:
                        pass
                else:
                    message_for_edit = await client.get_message(chat_instance[1], skype_content_list[str(content[1])]["discord_id"])
                    if not content[3]:
                        await client.edit_message(message_for_edit, new_content=content[0])
                    else:
                        await client.delete_message(message_for_edit)

# Endless loop that clear the messages list
# Messages will be saved for 1hour ... after this edit and delete is forbidden
# Because the message save is getting deleted for performance reason
async def cleaner_content_list():
    logger.warning("Start cleaner.")
    while client.is_logged_in:
        await asyncio.sleep(600)
        time_now = datetime.datetime.now()
        time_now = time_now - datetime.timedelta(hours=1, minutes=1)
        for mes_key in list(skype_content_list.items()):
            if mes_key[1]["time"] < time_now:
                del skype_content_list[mes_key[0]]

        for mes_key in list(discord_content_list.items()):
            if mes_key[1]["time"] < time_now:
                del discord_content_list[mes_key[0]]

@client.event
async def on_ready():
    print('Logged in as')
    print("Username:" + client.user.name)
    print("User ID:" + client.user.id)
    print("Version API: " + discord.__version__)
    print('------')
    # set current game played
    gameplayed = MAIN.get("gameplayed", "Yuri is Love")
    if gameplayed:
        game = discord.Game(name=gameplayed)
        await client.change_presence(game=game)

    # set avatar if specified
    avatar_file_name = MAIN.get("avatarfile")
    if avatar_file_name:
        with open(avatar_file_name, "rb") as f:
            avatar = f.read()
        await client.edit_profile(avatar=avatar)


    set_global_variables()
    asyncio.ensure_future(skype_loop())
    asyncio.ensure_future(cleaner_content_list())

@client.event
async def on_message(message):
    if message.content.startswith(""):
        try:
            server_id = message.server.id
            server_name = message.server.name
        except AttributeError:
            server_id = "0"
            server_name = "Private Message"

    if message.content.startswith(">>"):
        today = datetime.datetime.today()
        today = today.strftime(date_format)
        print(
            "Date: {} User: {} Server: {} Command {} ".format(today, message.author, server_name, message.content[:50]))

    # Search for messages that contain needed information
    if not message.content.startswith(">>") and not message.author.id in discord_id:
        if message.channel.id in ch:
            mes = message.content.replace("\n", "\n ").split(" ")
            user_name = message.author.name
            for index, x in enumerate(mes):
                if re.search("http", x):
                    mes[index] = f"<a href=\"{x}\">{x}</a>"
                emoji = re.match(rex, x)
                if emoji:
                    # uncomment this and you will send for each emoji a link with preview
                    #emoji_url = f"{discord_url}{emoji.group(2)}.png"
                    #emo = f"<a href=\"{emoji_url}\" >{emoji.group(1)}</a>>"

                    # this need to be commented with uncomment stuff above
                    emo = f"<b raw_pre=\"*\" raw_post=\"*\">{emoji.group(1)}</b>"
                    mes[index] = emo
                mention = re.match(rex_mention, x)
                if mention:
                    mention = await client.get_user_info(f"{mention.group(1)}")
                    mention = f"@{mention.name}"
                    mes[index] = mention
                mention_role = re.match(rex_mention_role, x)
                if mention_role:
                    for role in message.server.roles:
                        if role.id == mention_role.group(1):
                            mentioned_role = role
                    mention = f"@{mentioned_role.name} (Discord Role)"
                    mes[index] = mention
                mention_channel = re.match(rex_mention_channel, x)
                if mention_channel:
                    mention = client.get_channel(f"{mention_channel.group(1)}")
                    mention = f"#{mention.name}"
                    mes[index] = mention

            mes_full = " ".join(mes)
            # Search and replace {code}. Its not good when you allow this.
            mes_full = mes_full.replace("{code}", "```")
            if not message.attachments:
                content = f"<b raw_pre=\"*\" raw_post=\"*\">{user_name}: </b> {mes_full}"
            else:
                content = f"<b raw_pre=\"*\" raw_post=\"*\">{user_name}: </b> {mes_full}"
                for x in message.attachments:
                    content += f"<a href=\"{x['url']}\">{x['filename']}</a>"
            sky_mes = ch[str(message.channel.id)][0].sendMsg(content, rich=True)
            discord_content_list[message.id] = {
                "time": sky_mes.time,
                "skype_id": sky_mes,
            }

@client.event
async def on_message_edit(old_message, message):
    if not message.content.startswith(">>") and not message.author.id in discord_id:
        if message.channel.id in ch:
            mes = message.content.replace("\n", "\n ").split(" ")
            user_name = message.author.name
            for index, x in enumerate(mes):
                if re.search("http", x):
                    mes[index] = f"<a href=\"{x}\">{x}</a>"
                emoji = re.match(rex, x)
                if emoji:
                    # uncomment this and you will send for each emoji a link with preview
                    #emoji_url = f"{discord_url}{emoji.group(2)}.png"
                    #emo = f"<a href=\"{emoji_url}\" >{emoji.group(1)}</a>>"

                    # this need to be commented with uncomment stuff above
                    emo = f"<b raw_pre=\"*\" raw_post=\"*\">{emoji.group(1)}</b>"
                    mes[index] = emo
                mention = re.match(rex_mention, x)
                if mention:
                    mention = await client.get_user_info(f"{mention.group(1)}")
                    mention = f"@{mention.name}"
                    mes[index] = mention
                mention_role = re.match(rex_mention_role, x)
                if mention_role:
                    for role in message.server.roles:
                        if role.id == mention_role.group(1):
                            mentioned_role = role
                    mention = f"@{mentioned_role.name} (Discord Role)"
                    mes[index] = mention
                mention_channel = re.match(rex_mention_channel, x)
                if mention_channel:
                    mention = client.get_channel(f"{mention_channel.group(1)}")
                    mention = f"#{mention.name}"
                    mes[index] = mention

            mes_full = " ".join(mes)
            mes_full = mes_full.replace("{code}", "```")
            if not message.attachments:
                content = f"<b raw_pre=\"*\" raw_post=\"*\">{user_name}: </b> {mes_full}"
            else:
                content = f"<b raw_pre=\"*\" raw_post=\"*\">{user_name}: </b> {mes_full}"
                for x in message.attachments:
                    content += f"<a href=\"{x['url']}\"> {x['name']} </a>"
            old_mes = discord_content_list[old_message.id]
            sky_mes = old_mes["skype_id"].edit(content=content, rich=True)
            discord_content_list[message.id] = {
                "time": sky_mes.time,
                "skype_id": sky_mes,
            }


@client.event
async def on_message_delete(message):
    if not message.content.startswith(">>") and not message.author.id in discord_id:
        if message.channel.id in ch:
            old_mes = discord_content_list[message.id]
            old_mes["skype_id"].delete()

def main():
    client.run(MAIN.get("login_token"))
