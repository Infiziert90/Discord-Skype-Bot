import re
import skpy
import discord
import asyncio
import logging
from config import *
from collections import deque
from typing import Tuple, Deque


class Rex(dict):
    def __getitem__(self, item):
        return self.setdefault((item, 0), re.compile(item))

    def __setitem__(self, key, value):
        raise AttributeError('Rex objects are not supposed to be set')

    def get(self, k, flags=0):
        return self.setdefault((k, flags), re.compile(k, flags))
rex = Rex()


class ApplicationDiscord(discord.Client):
    def __init__(self,  **kwargs):
        super().__init__(**kwargs)
        self.discord_forbidden = []
        self.all_members = {}
        self.all_members_nick = {}
        self.message_dict = {}
        self.forward_q: Deque[Tuple[skpy.SkypeMsg, tuple, int]] = deque()
        self.skype = None
        self.start_tuple = None
        self.first_run = True
        self.loop_task = None

    def enque(self, msg, file, work):
        self.forward_q.append((msg, file, work))

    def run_loop(self):
        self.loop_task = asyncio.ensure_future(self.main_loop())

    async def main_loop(self):
        try:
            while True:
                await asyncio.sleep(0.01)  # all the other things
                while self.forward_q:
                    msg, file, work = self.forward_q.popleft()
                    msg.content = self.to_discord_format(msg.content)
                    if work == 1:
                        await self.discord_send_message(msg, file, work)
                    elif work == 2:
                        await self.discord_edit_message(msg, file, work)
                    else:
                        await self.discord_delete_message(msg, file, work)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logging.exception("exception in discord main loop")
            self.run_loop()

    async def on_ready(self):
        logging.info(f'Logged in \nUsername: {self.user.name}\nID: {self.user.id}\nAPI Version: {discord.__version__}')
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
            self.skype.discord = self
            for k, v in list(config.ch.items()):
                if v.isdigit():
                    config.ch[k] = self.get_channel(v)
            self.run_loop()

    # TODO Add embed support
    async def on_message(self, message):
        content = message.content
        if content.startswith(f"{config.MAIN.command_prefix}temp_bridge"):
            await self.create_temp_bridge(message)
        if content.startswith(self.start_tuple):
            return
        if message.author.id in self.discord_forbidden or message.author.name in self.discord_forbidden:
            return
        if message.channel in config.ch:
            content = await self.to_skype_format(content, message)
            self.skype.enque(message, content=content, work=1, new_msg=None)

    async def on_message_edit(self, old_message, message):
        content = message.content
        if content.startswith(self.start_tuple):
            return
        if message.author.id in self.discord_forbidden or message.author.name in self.discord_forbidden:
            return
        if message.channel in config.ch:
            content = await self.to_skype_format(content, message)
            self.skype.enque(old_message, content=content, work=2, new_msg=message)

    async def on_message_delete(self, message):
        content = message.content
        if content.startswith(self.start_tuple):
            return
        if message.author.id in self.discord_forbidden or message.author.name in self.discord_forbidden:
            return
        if message.channel in config.ch:
            self.skype.enque(message, content=None, work=3, new_msg=None)

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

    async def create_temp_bridge(self, msg: discord.Message):
        if msg.author.id in config.admin_id:
            content = msg.content.split(" ")
            if len(content) != 4:
                return await self.send_message(msg.channel, content="Input is not correct, pls check it again")

            first_id = content[2].split(":", 1)
            second_id = content[3].split(":", 1)
            if len(first_id) != 2 or len(second_id) != 2:
                return await self.send_message(msg.channel, content="ID input is not correct, pls check it again")

            if first_id[0] == "skype":
                skype_id = first_id[1]
                discord_id = second_id[1]
            elif first_id[0] == "discord":
                discord_id = first_id[1]
                skype_id = second_id[1]
            else:
                return await self.send_message(msg.channel, content="Input is not correct, pls check it again")

            if content[1] == "add":
                self.add_temp_bridge(skype_id, discord_id)
            elif content[1] == "delete":
                self.delete_temp_bridge(skype_id, discord_id)
            else:
                return await self.send_message(msg.channel, content="Method is not correct, pls check it again")

            await self.send_message(msg.channel, content="Done")

    def add_temp_bridge(self, skype_id: str, discord_id: str):
        config.ch[skype_id] = self.get_channel(discord_id)

    def delete_temp_bridge(self, skype_id, discord_id):
        config.ch.pop(skype_id, None)
        config.ch.pop(self.get_channel(discord_id), None)

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
            self.all_members[user.name.lower()] = user.id
            if hasattr('user', 'nick'):
                self.all_members_nick[user.nick.lower()] = user.id

    @staticmethod
    def embeds_to_skype_format(embeds) -> str:
        formated_embeds = "Embed:"
        for embed in embeds:
            title = embed.get("title", None)
            if title:
                formated_embeds += f"\n<b raw_pre=\"*\" raw_post=\"*\">Title: </b> {title}"
            description = embed.get("description", None)
            if description:
                formated_embeds += f"\n<b raw_pre=\"*\" raw_post=\"*\"> Description: </b> {description}"

        return formated_embeds

    # TODO Code blocks fix?
    async def to_skype_format(self, content, message) -> str:
        if message.author.bot and message.embeds:
            content = content.replace("[]()", "")
            content = f"{self.embeds_to_skype_format(message.embeds)}\n{content}"

        line_splits = content.split('\n')
        for li, line in enumerate(line_splits):
            word_splits = line.split(" ")
            for index, word in enumerate(word_splits):
                if "http" in word:
                    word_splits[index] = f"<a href=\"{word}\">{word}</a>"
                    continue
                if word in config.unicode_emoji:
                    try:
                        word_splits[index] = config.emoji[config.unicode_emoji[word]][1:-1]
                    except KeyError:
                        logging.warning(f"Missing emoji in emoji.json: {config.unicode_emoji[word]}")
                    continue

                emoji = re.match(rex["<:(\w+):(\d+)>"], word)
                if emoji:
                    if emoji.group(1) in config.emoji:
                        word_splits[index] = config.emoji[emoji.group(1)][1:-1]
                    else:
                        emo = f"<b raw_pre=\"*\" raw_post=\"*\">{emoji.group(1)}</b>"
                        word_splits[index] = emo
                    continue

                mention = re.match(rex["<@!?(\d+)>"], word)
                if mention:
                    mention = await self.get_user_info(mention.group(1))
                    mention = f"@{mention.name}"
                    word_splits[index] = mention
                    continue

                mention_role = re.match(rex["<@&(\d+)>"], word)
                if mention_role:
                    for role in message.server.roles:
                        if role.id == mention_role.group(1):
                            mentioned_role = role
                    mention = f"@{mentioned_role.name} (Discord Role)"
                    word_splits[index] = mention
                    continue

                mention_channel = re.match(rex["<#(\d+)>"], word)
                if mention_channel:
                    mention = self.get_channel(mention_channel.group(1))
                    mention = f"#{mention.name}"
                    word_splits[index] = mention

            line_splits[li] = " ".join(word_splits)
        content = '\n'.join(line_splits)
        content = f"<b raw_pre=\"*\" raw_post=\"*\">{message.author.nick if hasattr('message.author', 'nick') else message.author.name}: </b> {content}"
        if message.attachments:
            for word in message.attachments:
                content += f"\n<a href=\"{word['url']}\">{word['filename']}</a>"

        return content.replace("{code}", "```")

    def get_user_id(self, username):
        user_id = self.all_members.get(username, self.all_members_nick.get(username))
        if not user_id:
            self.fill_member_list()
            user_id = self.all_members.get(username, self.all_members_nick.get(username))

        return user_id

    # TODO Fix usernames with space
    # TODO Use re.finditer
    def to_discord_format(self, msg_content) -> str:
        msg_content = msg_content.replace("{code}", "```").replace("Edited previous message:", "")
        if "@" not in msg_content:
            return msg_content
        line_splits = msg_content.split('\n')
        for li, line in enumerate(line_splits):
            word_splits = line.split(" ")
            for index, sky_msg in enumerate(word_splits):
                username = re.match(rex["@(\w+)"], sky_msg)
                if username:
                    user_id = self.get_user_id(username.group(1).lower())
                    if user_id:
                        word_splits[index] = f"<@{user_id}> "

            line_splits[li] = " ".join(word_splits)
        return '\n'.join(line_splits)
