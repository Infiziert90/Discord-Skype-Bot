#!/usr/bin/python
# coding: utf-8
# Copyright (c) 2017 Toni Hänsel

import re
import sys
import skpy
import discord
import asyncio
import logging
from config import *
from collections import deque
from typing import Tuple, Deque

if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)


class Rex(dict):
    def __getitem__(self, item):
        return self.setdefault((item, 0), re.compile(item))

    def __setitem__(self, key, value):
        raise AttributeError('Rex objects are not supposed to be set')

    def get(self, k, flags=0):
        return self.setdefault((k, flags), re.compile(k, flags))

rex = Rex()


class AsyncSkype(skpy.SkypeEventLoop):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.forward_q: Deque[Tuple[discord.Message, int, discord.Message]] = deque()
        self.discord: ApplicationDiscord = None
        self.skype_forbidden = []
        self.get_forbidden_list()
        self.message_dict = {}
        self.run_loop()

    def enque(self, msg, work, new_msg=None):
        self.forward_q.append((msg, work, new_msg))

    def run_loop(self):
        asyncio.ensure_future(self.main_loop())

    async def main_loop(self):
        loop = asyncio.get_event_loop()
        cyc = asyncio.Future()
        cyc.set_result(0)
        try:
            while True:
                await asyncio.sleep(.3)
                if cyc.done():
                    cyc = asyncio.ensure_future(loop.run_in_executor(None, self.cycle))
                while self.forward_q:
                    msg, work, new_msg = self.forward_q.popleft()
                    if work == 1:
                        self.send_message(msg, work, new_msg)
                    elif work == 2:
                        self.edit_message(msg, work, new_msg)
                    else:
                        self.delete_message(msg, work, new_msg)
                    await asyncio.sleep(.1)
        except Exception as e:
            logging.exception("Exception in skype main loop")
            self.run_loop()

    def onEvent(self, event):
        if hasattr(event, "msg") and event.msg.user.id in self.skype_forbidden:
            return
        if isinstance(event, skpy.SkypeNewMessageEvent):
            event.msg.content = self.inspect_skype_content(event.msg)
            self.discord.enque(event.msg, work=1)
        elif isinstance(event, skpy.SkypeEditMessageEvent):
            content = self.inspect_skype_content_edit(event.msg)
            event.msg.content = content
            self.discord.enque(event.msg, work=3 if event.msg.deleted else 2)

    def send_message(self, msg, work, new_msg):
        try:
            skype_message = self.chats[f"{config.ch[msg.channel]}"].sendMsg(msg.content, rich=True)
            self.update_internal_msg(skype_message, msg)
        except Exception as e:
            logging.exception("Exception in skype send_message")
            self.forward_q.append((msg, work, new_msg))

    def edit_message(self, msg: discord.Message, work, new_msg):
        if msg.id not in self.message_dict:
            return
        try:
            skype_message = self.message_dict[msg.id].edit(content=new_msg.content, rich=True)
            del self.message_dict[msg.id]
            self.update_internal_msg(skype_message, new_msg)
        except Exception as e:
            logging.exception("Exception in skype edit_message")
            self.forward_q.append((msg, work, new_msg))


    def delete_message(self, msg, work, new_msg):
        if msg.id not in self.message_dict:
            return
        try:
            self.message_dict[msg.id].delete()
            del self.message_dict[msg.id]
        except Exception as e:
            logging.exception("Exception in skype delete_message")
            self.forward_q.append((msg, work, new_msg))

    def update_internal_msg(self, skype_msg_obj, discord_msg_obj):
        self.message_dict[discord_msg_obj.id] = skype_msg_obj
        asyncio.get_event_loop().call_later(3600, lambda : self.message_dict.pop(discord_msg_obj.id, None))

    def get_forbidden_list(self):
        self.skype_forbidden = [self.user.id]
        for x in config["FORBIDDEN_SKYPE"].values():
            self.skype_forbidden.append(str(x))
        logging.info(f"Forbidden Skype:\n{self.skype_forbidden}")

    def inspect_skype_content(self, message: skpy.SkypeMsg) -> str:
        if isinstance(message, skpy.SkypeTextMsg):
            message_con = self.edit_skype_message(message)
            return f"**{message.user.name}**: {message_con}"
        elif isinstance(message, skpy.SkypeAddMemberMsg):
            return f"**{message.user.name}** joined the chat in skype!"
        elif isinstance(message, skpy.SkypeRemoveMemberMsg):
            mes = message.content.split("<target>")[1]
            mes = mes.split("</target>")[0]
            mes = mes[2:]
            return f"**{mes}** was removed from the chat in skype!"
        elif isinstance(message, skpy.SkypeFileMsg):
            mes = message.content.split("url_thumbnail=\"")[1]
            mes = mes.split("\"")[0]
            return f"**{message.user.name}** sended a file ... here the preview {mes}"
        elif isinstance(message, skpy.SkypeImageMsg):
            mes = message.content.split("url_thumbnail=\"")[1]
            mes = mes.split("\"")[0]
            return f"**{message.user.name}** sended a file ... here the preview {mes}"

    def inspect_skype_content_edit(self, message) -> str:
        if message.content:
            message_con = self.edit_skype_message(message)
            message_con = message_con.replace("Edited previous message:", "")
            return f"**{message.user.name}**: {message_con}"
        else:
            return ""

    # From skpy
    def markup(self, x):
        if x.content is None:
            return None
        text = re.sub(rex["<e.*?/>"], "", x.content)
        text = re.sub(rex["</?b.*?>"], "*", text)
        text = re.sub(rex["</?i.*?>"], "_", text)
        text = re.sub(rex["</?s.*?>"], "~", text)
        text = re.sub(rex["</?pre.*?>"], "{code}", text)
        text = re.sub(rex['<a.*?href="(.*?)">.*?</a>'], r"\1", text)
        text = re.sub(rex['<at.*?id="8:(.*?)">.*?</at>'], r"@\1", text)
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&") \
            .replace("&quot;", "\"").replace("&apos;", "'")
        return text

    def edit_skype_message(self, message):
        right_mes = ""
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

        skype_con = self.markup(message)
        skype_con = skype_con.split(" ")
        user_id = []
        # Search and replace user mention with the discord code for mentions
        for index, sky_mes in enumerate(skype_con):
            if sky_mes in config.emoji:
                if "|"  in config.emoji[sky_mes]:
                    skype_con[index] = f":{config.emoji[sky_mes][:-2]}:"
                else:
                    skype_con[index] = f":{config.emoji[sky_mes]}:"
            username = re.match(rex["@(\w+)"], sky_mes)
            if username:
                for user in self.discord.client.get_all_members():
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


class ApplicationDiscord(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.discord_forbidden = []
        self.forward_q: Deque[Tuple[skpy.SkypeMsg, int]] = deque()
        self.message_dict = {}
        self.Skype = None
        self.start_tuple = None

    def enque(self, msg, work):
        self.forward_q.append((msg, work))

    def run_loop(self):
        asyncio.ensure_future(self.main_loop())

    async def main_loop(self):
        try:
            while True:
                await asyncio.sleep(0.01)  # all the other things
                while self.forward_q:
                    msg, work= self.forward_q.popleft()
                    if work == 1:
                        await self.discord_send_message(msg, work)
                    elif work == 2:
                        await self.discord_edit_message(msg, work)
                    else:
                        await self.discord_delete_message(msg, work)
        except Exception as e:
            logging.exception("exception in discord main loop")
            self.run_loop()

    async def on_ready(self):
        logging.info(f'Logged in as\nUsername: {self.user.name}\nID: {self.user.id}\nAPI Version: {discord.__version__}')
        gameplayed = config.MAIN.get("gameplayed", "Yuri is Love")
        if gameplayed:
            game = discord.Game(name=gameplayed)
            await self.change_presence(game=game)
        avatar_file_name = config.MAIN.get("avatarfile")
        if avatar_file_name:
            with open(avatar_file_name, "rb") as f:
                avatar = f.read()
            await self.edit_profile(avatar=avatar)
        self.get_forbidden_list()
        self.get_startswith()
        self.Skype = AsyncSkype(config.MAIN.skype_email, config.MAIN.skype_password)
        self.Skype.discord = self
        for k, v in config.ch.items():
            if v.isdigit():
                config.ch[k] = self.get_channel(v)
        self.run_loop()

    async def on_message(self, message):
        content = message.content
        if not content.startswith(self.start_tuple) and not message.author.id in self.discord_forbidden and not message.author.name in self.discord_forbidden:
            if message.channel in config.ch:
                message.content = await self.edit_discord_message(content, message)
                self.Skype.enque(message, work=1, new_msg=None)

    async def on_message_edit(self, old_message, message):
        content = message.content
        if not message.content.startswith(self.start_tuple) and not message.author.id in self.discord_forbidden:
            if message.channel in config.ch:
                message.content = await self.edit_discord_message(content, message)
                self.Skype.enque(old_message, work=2, new_msg=message)


    async def on_message_delete(self, message):
        if not message.content.startswith(self.start_tuple) and not message.author.id in self.discord_forbidden:
            if message.channel in config.ch:
                self.Skype.enque(message, work=3, new_msg=None)

    async def discord_send_message(self, msg, work):
        try:
            discord_message = await self.send_message(config.ch[msg.chat.id], msg.content)
            self.update_internal_msg(msg, discord_message)
        except Exception as e:
            logging.exception("Exception while sending discord message")
            self.forward_q.append((msg, work))

    async def discord_edit_message(self, msg: skpy.SkypeMsg, work):
        if msg.clientId not in self.message_dict:
            return
        try:
            discord_message = await self.edit_message(self.message_dict[msg.clientId], new_content=msg.content)
            self.update_internal_msg(msg, discord_message)
        except Exception as e:
            logging.exception("Exception in discord_edit_message")
            self.forward_q.append((msg, work))

    async def discord_delete_message(self, msg, work):
        if msg.clientId not in self.message_dict:
            return
        try:
            await self.delete_message(self.message_dict[msg.clientId])
        except Exception as e:
            logging.exception("Exception in discord_delete_message")
            self.forward_q.append((msg, work))

    def update_internal_msg(self, skype_msg_obj: skpy.SkypeMsg, discord_msg_obj):
        self.message_dict[skype_msg_obj.clientId] = discord_msg_obj
        asyncio.get_event_loop().call_later(3600, lambda : self.message_dict.pop(skype_msg_obj.clientId, None))

    def get_forbidden_list(self):
        self.discord_forbidden = [self.user.id]
        for x in config["FORBIDDEN_DISCORD"].values():
            self.discord_forbidden.append(str(x))
        logging.info(f"Forbidden Discord:\n{self.discord_forbidden}")

    async def edit_discord_message(self, content, message):
        splitted_message = content.replace("\n", "\n ").split(" ")
        for index, x in enumerate(splitted_message):
            if re.search("http", x):
                splitted_message[index] = f"<a href=\"{x}\">{x}</a>"
                continue
            emoji = re.match(rex["<:(\w+):(\d+)>"], x)
            if x in config.unicode_emoji:
                splitted_message[index] = f"{config.emoji[config.unicode_emoji[x]][1:-1]}"
            if emoji:
                if emoji.group(1) in config.emoji:
                    splitted_message[index] = f"{config.emoji[emoji.group(1)][1:-1]}"
                    continue
                emo = f"<b raw_pre=\"*\" raw_post=\"*\">{emoji.group(1)}</b>"
                splitted_message[index] = emo
                continue
            mention = re.match(rex["<@!?(\d+)>"], x)
            if mention:
                mention = await self.get_user_info(f"{mention.group(1)}")
                mention = f"@{mention.name}"
                splitted_message[index] = mention
                continue
            mention_role = re.match(rex["<@&(\d+)>"], x)
            if mention_role:
                for role in message.server.roles:
                    if role.id == mention_role.group(1):
                        mentioned_role = role
                mention = f"@{mentioned_role.name} (Discord Role)"
                splitted_message[index] = mention
                continue
            mention_channel = re.match(rex["<#(\d+)>"], x)
            if mention_channel:
                mention = self.get_channel(f"{mention_channel.group(1)}")
                mention = f"#{mention.name}"
                splitted_message[index] = mention
        content = " ".join(splitted_message)
        content = content.replace("{code}", "```")
        if not message.attachments:
            content = f"<b raw_pre=\"*\" raw_post=\"*\">{message.author.name}: </b> {content}"
        else:
            content = f"<b raw_pre=\"*\" raw_post=\"*\">{message.author.name}: </b> {content}"
            for x in message.attachments:
                content += f"<a href=\"{x['url']}\">{x['filename']}</a>"

        return content

    def get_startswith(self):
        start_list = []
        for word in config.FORBIDDEN_START.values():
            start_list.append(word)
        self.start_tuple = tuple(start_list)
        logging.info(f"Forbidden Start:\n{self.start_tuple}")


def main():
    load_config()
    logging.info("Start discord run")
    app = ApplicationDiscord()
    app.run(config.MAIN.login_token)

if __name__ == "__main__":
    main()