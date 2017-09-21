#!/usr/bin/python
# coding: utf-8
# Copyright (c) 2017 Toni Hänsel

import sys
import skpy
import discord
import asyncio
import logging
from config import *
from collections import deque
from typing import Tuple, Deque
from message_edit import EditMessage

if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)

# TODO fix "Couldn't retrieve PPFT from login form" error
class AsyncSkype(skpy.SkypeEventLoop):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.forward_q: Deque[Tuple[discord.Message, str, int, discord.Message]] = deque()
        self.discord: ApplicationDiscord = None
        self.skype_forbidden = []
        self.get_forbidden_list()
        self.message_dict = {}
        self.EditMessage: EditMessage = None
        self.run_loop()

    def enque(self, msg, content, work, new_msg=None):
        self.forward_q.append((msg, content, work, new_msg))

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
                    msg, content, work, new_msg = self.forward_q.popleft()
                    if work == 1:
                        self.send_message(msg, content, work, new_msg)
                    elif work == 2:
                        self.edit_message(msg, content, work, new_msg)
                    else:
                        self.delete_message(msg, content, work, new_msg)
                    await asyncio.sleep(.1)
        except Exception as e:
            logging.exception("Exception in skype main loop")
            self.run_loop()

    def onEvent(self, event):
        if not hasattr(event, "msg") or event.msg.user.id in self.skype_forbidden:
            return

        if event.msg.chat.id in config.ch:
            if isinstance(event, skpy.SkypeEditMessageEvent):
                event.msg.content = self.EditMessage.inspect_skype_content_edit(event.msg)
                self.discord.enque(event.msg, file=None, work=2 if event.msg.content else 3)
            elif isinstance(event.msg, skpy.SkypeTextMsg):
                event.msg.content = self.EditMessage.inspect_skype_content(event.msg)
                self.discord.enque(event.msg, file=None, work=1)
            elif isinstance(event.msg, skpy.SkypeAddMemberMsg):
                event.msg.content = f"**{event.msg.member.name}** joined the chat in skype!"
                self.discord.enque(event.msg, file=None, work=1)
            elif isinstance(event.msg, skpy.SkypeRemoveMemberMsg):
                event.msg.content = f"**{event.msg.member.name}** was removed from the chat in skype!"
                self.discord.enque(event.msg, file=None, work=1)
            elif isinstance(event.msg, skpy.SkypeImageMsg):
                event.msg.content, sky_file = self.EditMessage.skype_image_message(event.msg)
                self.discord.enque(event.msg, file=sky_file, work=1)
            elif isinstance(event.msg, skpy.SkypeFileMsg):
                event.msg.content, sky_file = self.EditMessage.skype_file_message(event.msg)
                self.discord.enque(event.msg, file=sky_file, work=1)

    def send_message(self, msg, content, work, new_msg):
        try:
            skype_message = self.chats[f"{config.ch[msg.channel]}"].sendMsg(content, rich=True)
            self.update_internal_msg(skype_message, msg)
        except Exception as e:
            logging.exception("Exception in skype send_message")
            self.forward_q.append((msg, content, work, new_msg))

    def edit_message(self, msg: discord.Message, content, work, new_msg):
        if msg.id not in self.message_dict:
            return
        try:
            skype_message = self.message_dict[msg.id].edit(content=content, rich=True)
            del self.message_dict[msg.id]
            self.update_internal_msg(skype_message, new_msg)
        except Exception as e:
            logging.exception("Exception in skype edit_message")
            self.forward_q.append((msg, content, work, new_msg))

    def delete_message(self, msg, content, work, new_msg):
        if msg.id not in self.message_dict:
            return
        try:
            self.message_dict[msg.id].delete()
            del self.message_dict[msg.id]
        except Exception as e:
            logging.exception("Exception in skype delete_message")
            self.forward_q.append((msg, content, work, new_msg))

    def update_internal_msg(self, skype_msg_obj, discord_msg_obj):
        self.message_dict[discord_msg_obj.id] = skype_msg_obj
        asyncio.get_event_loop().call_later(36000, lambda: self.message_dict.pop(discord_msg_obj.id, None))

    def get_forbidden_list(self):
        self.skype_forbidden = [self.user.id]
        for x in config["FORBIDDEN_SKYPE"].values():
            self.skype_forbidden.append(str(x))
        logging.info(f"Forbidden Skype:\n{self.skype_forbidden}")


class ApplicationDiscord(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.discord_forbidden = []
        self.all_members = {}
        self.all_members_nick = {}
        self.message_dict = {}
        self.forward_q: Deque[Tuple[skpy.SkypeMsg, tuple, int]] = deque()
        self.Skype: AsyncSkype = None
        self.EditMessage: EditMessage = None
        self.start_tuple = None
        self.first_run = True

    def enque(self, msg, file, work):
        self.forward_q.append((msg, file, work))

    def run_loop(self):
        asyncio.ensure_future(self.main_loop())

    async def main_loop(self):
        try:
            while True:
                await asyncio.sleep(0.01)  # all the other things
                while self.forward_q:
                    msg, file, work = self.forward_q.popleft()
                    if work == 1:
                        await self.discord_send_message(msg, file, work)
                    elif work == 2:
                        await self.discord_edit_message(msg, file, work)
                    else:
                        await self.discord_delete_message(msg, file, work)
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
        if self.first_run:
            self.first_run = False
            self.get_forbidden_list()
            self.get_startswith()
            self.fill_member_list()
            self.Skype = AsyncSkype(config.MAIN.skype_email, config.MAIN.skype_password)
            self.Skype.discord = self
            self.EditMessage = EditMessage()
            self.EditMessage.discord = self
            self.Skype.EditMessage = self.EditMessage
            for k, v in list(config.ch.items()):
                if v.isdigit():
                    config.ch[k] = self.get_channel(v)
            self.run_loop()

    # TODO Add embed support
    async def on_message(self, message):
        content = message.content
        if content.startswith(self.start_tuple) or message.author.id in self.discord_forbidden or message.author.name in self.discord_forbidden:
            return
        if message.channel in config.ch:
            content = await self.EditMessage.edit_discord_message(content, message)
            self.Skype.enque(message, content=content, work=1, new_msg=None)

    async def on_message_edit(self, old_message, message):
        content = message.content
        if content.startswith(self.start_tuple) or message.author.id in self.discord_forbidden or message.author.name in self.discord_forbidden:
            return
        if message.channel in config.ch:
            content = await self.EditMessage.edit_discord_message(content, message)
            self.Skype.enque(old_message, content=content, work=2, new_msg=message)

    async def on_message_delete(self, message):
        content = message.content
        if content.startswith(self.start_tuple) or message.author.id in self.discord_forbidden or message.author.name in self.discord_forbidden:
            return
        if message.channel in config.ch:
            self.Skype.enque(message, content=None, work=3, new_msg=None)

    async def discord_send_message(self, msg, file, work):
        try:
            if file:
                discord_message = await self.send_file(config.ch[msg.chat.id], file[0], filename=file[1], content=msg.content)
            else:
                discord_message = await self.send_message(config.ch[msg.chat.id], msg.content)
            self.update_internal_msg(msg, discord_message)
        except KeyError:
            logging.warning("Deleted a message from unkown chat.")
        except Exception as e:
            logging.exception("Exception while sending discord message")
            self.forward_q.append((msg, file, work))

    async def discord_edit_message(self, msg, file, work):
        if msg.clientId not in self.message_dict:
            return
        try:
            discord_message = await self.edit_message(self.message_dict[msg.clientId], new_content=msg.content)
            self.update_internal_msg(msg, discord_message)
        except Exception as e:
            logging.exception("Exception in discord_edit_message")
            self.forward_q.append((msg, file, work))

    async def discord_delete_message(self, msg, file, work):
        if msg.clientId not in self.message_dict:
            return
        try:
            await self.delete_message(self.message_dict[msg.clientId])
        except Exception as e:
            logging.exception("Exception in discord_delete_message")
            self.forward_q.append((msg, file, work))

    def update_internal_msg(self, skype_msg_obj: skpy.SkypeMsg, discord_msg_obj):
        self.message_dict[skype_msg_obj.clientId] = discord_msg_obj
        asyncio.get_event_loop().call_later(36000, lambda: self.message_dict.pop(skype_msg_obj.clientId, None))

    def get_forbidden_list(self):
        self.discord_forbidden = [self.user.id]
        for x in config["FORBIDDEN_DISCORD"].values():
            self.discord_forbidden.append(str(x))
        logging.info(f"Forbidden Discord:\n{self.discord_forbidden}")

    def get_startswith(self):
        start_list = []
        for word in config.FORBIDDEN_START.values():
            start_list.append(word)
        self.start_tuple = tuple(start_list)
        logging.info(f"Forbidden Start:\n{self.start_tuple}")

    def fill_member_list(self):
        for user in self.get_all_members():
            self.all_members[user.name] = user.id
            if user.nick:
                self.all_members_nick[user.nick] = user.id


def main():
    load_config()
    logging.info("Start discord run")
    app = ApplicationDiscord()
    app.run(config.MAIN.login_token)


if __name__ == "__main__":
    main()
