#!/usr/bin/python
# coding: utf-8
# Copyright (c) 2017 Toni Hänsel

import re
import io
import skpy
import logging
from config import *
from bs4 import BeautifulSoup
from datetime import datetime


class Rex(dict):
    def __getitem__(self, item):
        return self.setdefault((item, 0), re.compile(item))

    def __setitem__(self, key, value):
        raise AttributeError('Rex objects are not supposed to be set')

    def get(self, k, flags=0):
        return self.setdefault((k, flags), re.compile(k, flags))
rex = Rex()


class EditMessage:
    def __init__(self):
        self.discord_client = None

    # From skpy
    def markup(self, x: skpy.SkypeMsg):
        if x.content is None:
            return None

        text = re.sub(rex["<e.*?/>"], "", x.content)
        text = re.sub(rex["</?b.*?>"], "*", text)
        text = re.sub(rex["</?i.*?>"], "_", text)
        text = re.sub(rex["</?s.*?>"], "~", text)
        text = re.sub(rex["</?pre.*?>"], "{code}", text)
        text = re.sub(rex['<a.*?href="(.*?)">.*?</a>'], r"\1", text)
        text = re.sub(rex['<at.*?id="8:(.*?)">.*?</at>'], r"@\1", text)
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", "\"").replace("&apos;", "'")
        return text

    def inspect_skype_content(self, message: skpy.SkypeMsg) -> str:
        message_con = self.edit_skype_message(message)
        return f"**{message.user.name}**: {message_con}"

    def inspect_skype_content_edit(self, message: skpy.SkypeMsg) -> str:
        if not message.content:
            return ""

        if "<e_m ts=\"" in message.content:
            if len(message.content.split("<e_m ts=\"")[0]) > 25:
                message_con = self.edit_skype_message(message)
                return f"**{message.user.name}**: {message_con}"
            else:
                return ""
        else:
            message_con = self.edit_skype_message(message)
            return f"**{message.user.name}**: {message_con}"

    @staticmethod
    def skype_image_message(message: skpy.SkypeMsg) -> tuple:
        sky_file = io.BytesIO(message.fileContent)
        if sky_file.getbuffer().nbytes <= 8388222:
            sky_name = message.file.name
            file_tuple = (sky_file, sky_name)
            return f"From **{message.user.name}**:", file_tuple
        return f"From **{message.user.name}**:\n Can't send picture, 8mb limit, thx discord.", None

    @staticmethod
    def skype_file_message(message: skpy.SkypeMsg) -> tuple:
        if int(message.file.size) <= 8388222:
            sky_file = io.BytesIO(message.fileContent)
            sky_name = message.file.name
            file_tuple = (sky_file, sky_name)
            return f"From **{message.user.name}**:", file_tuple
        return f"From **{message.user.name}**:\n Can't send file, 8mb limit, thx discord.", None

    # TODO WebSkype quote emojis broken
    # TODO Uniform time appearance
    @staticmethod
    def edit_skype_quote(message) -> str:
        right_mes = ""
        match_next = False
        soup = BeautifulSoup(message, "html.parser")
        for string_text in soup.find_all(text=True):
            if re.search(rex["\[.*?\d+:\d+:\d+\]"], string_text):
                right_mes += f"\n```{string_text}\n"
                match_next = True
            elif re.search(rex["\[\d{10}\]"], string_text):
                timestamp = re.search(rex["\[\d{10}\]"], string_text)
                correct_date = datetime.fromtimestamp(int(timestamp.group()[1:-1])).strftime('%H:%M:%S')
                string_text = re.sub(rex["\[\d{10}\]"], f"[{correct_date}]", string_text)
                right_mes += f"```{string_text}\n"
                match_next = True
            elif re.search(rex["\[.*?\d+:\d+:\d+ \D+\]"], string_text):
                time = re.search(rex["\[.*?\d+:\d+:\d+ \D+\]"], string_text)
                correct_date = datetime.strptime(time.group()[1:-1], "%I:%M:%S %p").strftime("%H:%M:%S")
                string_text = re.sub(rex["\[.*?\d+:\d+:\d+ \D+\]"], f"[{correct_date}]", string_text)
                right_mes += f"```{string_text}\n"
                match_next = True
            elif "<<<" in string_text:
                pass
            elif match_next:
                right_mes += f"{string_text}```\n\n"
                match_next = False
            else:
                right_mes += f"{string_text}"

        return right_mes

    @staticmethod
    def edit_skype_emoji(message) -> str:
        message = message.replace("~(", " ~(").replace(")~", ")~ ").replace("\n", ";;|||;;").split(" ")
        for index, sky_msg in enumerate(message):
            emoji = re.match(rex["~.*?~"], sky_msg)
            if emoji:
                if emoji.group() in config.emoji:
                    emoji = config.emoji[emoji.group()].split("|")[0]
                    message[index] = f":{emoji}:"
                else:
                    logging.warning(f"Missing Emoji {emoji.group()} in emoji.json.")

        return " ".join(message)

    def get_user_id(self, username):
        user_id = self.discord_client.all_members.get(username, self.discord_client.all_members_nick.get(username))
        if not user_id:
            self.discord_client.fill_member_list()
            user_id = self.discord_client.all_members.get(username, self.discord_client.all_members_nick.get(username))

        return user_id

    # TODO Fix usernames with space
    # TODO Use re.finditer
    def edit_skype_mention(self, message) -> str:
        message = message.replace("\n", ";;|||;;").split(" ")
        for index, sky_msg in enumerate(message):
            username = re.match(rex["(@\w+)"], sky_msg)
            if username:
                user_id = self.get_user_id(username.group(1).lower())
                if user_id:
                    message[index] = f"<@{user_id}> "

        return " ".join(message)

    def edit_skype_message(self, message: skpy.SkypeMsg) -> str:
        msg_content = self.markup(message)
        if "</quote>" in msg_content:
            msg_content = self.edit_skype_quote(msg_content)

        if "~" in msg_content:
            msg_content = self.edit_skype_emoji(msg_content)

        if "@" in msg_content:
            msg_content = self.edit_skype_mention(msg_content)
        msg_content = msg_content.replace("{code}", "```").replace(";;|||;;", "\n").replace("Edited previous message:", "")

        return msg_content

    # TODO cleanup
    async def edit_discord_message(self, content, message) -> str:
        splitted_message = content.replace("\n", ";;|||;;").split(" ")
        for index, word in enumerate(splitted_message):
            if re.search("http", word):
                splitted_message[index] = f"<a href=\"{word}\">{word}</a>"
                continue

            if word in config.unicode_emoji:
                try:
                    splitted_message[index] = config.emoji[config.unicode_emoji[word]][1:-1]
                except KeyError as e:
                    logging.warning(f"Missing emoji in emoji.json: {config.unicode_emoji[word]}")
                continue

            emoji = re.match(rex["<:(\w+):(\d+)>"], word)
            if emoji:
                if emoji.group(1) in config.emoji:
                    splitted_message[index] = config.emoji[emoji.group(1)][1:-1]
                else:
                    emo = f"<b raw_pre=\"*\" raw_post=\"*\">{emoji.group(1)}</b>"
                    splitted_message[index] = emo
                continue

            mention = re.match(rex["<@!?(\d+)>"], word)
            if mention:
                mention = await self.discord_client.get_user_info(mention.group(1))
                mention = f"@{mention.name}"
                splitted_message[index] = mention
                continue

            mention_role = re.match(rex["<@&(\d+)>"], word)
            if mention_role:
                for role in message.server.roles:
                    if role.id == mention_role.group(1):
                        mentioned_role = role
                mention = f"@{mentioned_role.name} (Discord Role)"
                splitted_message[index] = mention
                continue

            mention_channel = re.match(rex["<#(\d+)>"], word)
            if mention_channel:
                mention = self.discord_client.get_channel(mention_channel.group(1))
                mention = f"#{mention.name}"
                splitted_message[index] = mention

        content = " ".join(splitted_message)
        content = content.replace("{code}", "```").replace(";;|||;;", "\n")
        content = f"<b raw_pre=\"*\" raw_post=\"*\">{message.author.name}: </b> {content}"
        if message.attachments:
            for word in message.attachments:
                content += f"\n<a href=\"{word['url']}\">{word['filename']}</a>"

        return content
