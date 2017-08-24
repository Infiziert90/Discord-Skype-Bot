#!/usr/bin/python
# coding: utf-8
# Copyright (c) 2017 Toni Hänsel

import re
import skpy
from config import *


class Rex(dict):
    def __getitem__(self, item):
        return self.setdefault((item, 0), re.compile(item))

    def __setitem__(self, key, value):
        raise AttributeError('Rex objects are not supposed to be set')

    def get(self, k, flags=0):
        return self.setdefault((k, flags), re.compile(k, flags))

rex = Rex()


class EditMessage():
    def __init__(self):
        self.discord = None

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

    def inspect_skype_content_edit(self, message: skpy.SkypeMsg) -> str:
        try:
            if "<e_m ts=\"" in message.content:
                if len(message.content.split("<e_m ts=\"")[0]) > 25:
                    message_con = self.edit_skype_message(message)
                    return f"**{message.user.name}**: {message_con}"
                else:
                    return ""
            else:
                message_con = self.edit_skype_message(message)
                return f"**{message.user.name}**: {message_con}"
        except TypeError:
            return ""

    def edit_skype_message(self, message: skpy.SkypeMsg):
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
        # Search and replace user mention with the discord code for mentions
        for index, sky_msg in enumerate(skype_con):
            if sky_msg in config.emoji:
                if "|"  in config.emoji[sky_msg]:
                    skype_con[index] = f":{config.emoji[sky_msg][:-2]}:"
                    continue
                else:
                    skype_con[index] = f":{config.emoji[sky_msg]}:"
                    continue
            username = re.match(rex["@(\w+)"], sky_msg)
            if username:
                user_id = None
                if username.group(1) in self.discord.all_members:
                    user_id = self.discord.all_members[username.group(1)]
                elif username.group(1) in self.discord.all_members_nick:
                    user_id = self.discord.all_members_nick[username.group(1)]
                else:
                    self.discord.fill_member_list()
                    if username.group(1) in self.discord.all_members:
                        user_id = self.discord.all_members[username.group(1)]
                    elif username.group(1) in self.discord.all_members_nick:
                        user_id = self.discord.all_members_nick[username.group(1)]

                if user_id:
                    skype_con[index] = f"<@{user_id}> "

        message_con = " ".join(skype_con)
        message_con = message_con.replace("{code}", "```").replace("&lt;&lt;&lt;", "").replace("Edited previous message:", "")

        return message_con

    async def edit_discord_message(self, content, message):
        splitted_message = content.replace("\n", " \n ").split(" ")
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
                mention = await self.discord.get_user_info(f"{mention.group(1)}")
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
                mention = self.discord.get_channel(f"{mention_channel.group(1)}")
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
