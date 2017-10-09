import io
from bs4 import BeautifulSoup
from datetime import datetime
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


class AsyncSkype(skpy.SkypeEventLoop):
    def __init__(self, *args, forward_q=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.forward_q: Deque[Tuple[discord.Message, str, int, discord.Message]] = forward_q or deque()
        self.discord = None
        self.skype_forbidden = []
        self.get_forbidden_list()
        self.message_dict = {}
        self.dead = False
        self.refresh_token()
        asyncio.ensure_future(self.main_loop())

    @classmethod
    def reinstanciate(cls, current):
        new_skype = AsyncSkype(config.MAIN.skype_email, config.MAIN.skype_password, forward_q=current.forward_q)
        current.discord.skype = new_skype
        new_skype.discord = current.discord

    def enque(self, msg, content, work, new_msg=None):
        self.forward_q.append((msg, content, work, new_msg))

    def refresh_token(self):
        asyncio.get_event_loop().call_later(82800, self.conn.refreshSkypeToken)
        asyncio.get_event_loop().call_later(82800, self.refresh_token)

    async def main_loop(self):
        loop = asyncio.get_event_loop()
        cyc = asyncio.Future()
        cyc.set_result(0)
        try:
            while not self.dead:
                await asyncio.sleep(.3)
                if cyc.done():
                    cyc = asyncio.ensure_future(loop.run_in_executor(None, self.cycle))
                while self.forward_q and not self.dead:
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
            self.dead = True

        if self.dead:
            self.reinstanciate(self)

    def onEvent(self, event):
        if not hasattr(event, "msg") or event.msg.user.id in self.skype_forbidden:
            return

        if event.msg.chat.id in config.ch:
            if type(event) == skpy.SkypeEditMessageEvent:
                event.msg.content = self.inspect_skype_editmsg_content(event.msg)
                self.discord.enque(event.msg, file=None, work=2 if event.msg.content else 3)
            elif type(event.msg) == skpy.SkypeTextMsg:
                event.msg.content = self.inspect_skype_msg_content(event.msg)
                self.discord.enque(event.msg, file=None, work=1)
            elif type(event.msg) == skpy.SkypeAddMemberMsg:
                event.msg.content = f"**{event.msg.member.name}** joined the chat in skype!"
                self.discord.enque(event.msg, file=None, work=1)
            elif type(event.msg) == skpy.SkypeRemoveMemberMsg:
                event.msg.content = f"**{event.msg.member.name}** was removed from the chat in skype!"
                self.discord.enque(event.msg, file=None, work=1)
            elif type(event.msg) == skpy.SkypeImageMsg:
                event.msg.content, sky_file = self.skype_to_discord_image(event.msg)
                self.discord.enque(event.msg, file=sky_file, work=1)
            elif type(event.msg) == skpy.SkypeFileMsg:
                event.msg.content, sky_file = self.skype_to_discord_file(event.msg)
                self.discord.enque(event.msg, file=sky_file, work=1)

    def send_message(self, msg, content, work, new_msg):
        try:
            skype_message = self.chats[f"{config.ch[msg.channel]}"].sendMsg(content, rich=True)
            self.update_internal_msg(skype_message, msg)
        except Exception as e:
            logging.exception("Exception in skype send_message")
            self.forward_q.append((msg, content, work, new_msg))
            self.dead = True

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
            self.dead = True

    def delete_message(self, msg, content, work, new_msg):
        if msg.id not in self.message_dict:
            return
        try:
            self.message_dict[msg.id].delete()
            del self.message_dict[msg.id]
        except Exception as e:
            logging.exception("Exception in skype delete_message")
            self.forward_q.append((msg, content, work, new_msg))
            self.dead = True

    def update_internal_msg(self, skype_msg_obj, discord_msg_obj):
        self.message_dict[discord_msg_obj.id] = skype_msg_obj
        asyncio.get_event_loop().call_later(36000, lambda: self.message_dict.pop(discord_msg_obj.id, None))

    def get_forbidden_list(self):
        self.skype_forbidden = [self.user.id]
        for x in config["FORBIDDEN_SKYPE"].values():
            self.skype_forbidden.append(str(x))
        logging.info(f"Forbidden Skype:\n{self.skype_forbidden}")

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

    def inspect_skype_msg_content(self, message: skpy.SkypeMsg) -> str:
        message_con = self.to_discord_format(message)
        return f"**{message.user.name}**: {message_con}"

    def inspect_skype_editmsg_content(self, message: skpy.SkypeMsg) -> str:
        if not message.content:
            return ""

        if "<e_m ts=\"" in message.content:
            if len(message.content.split("<e_m ts=\"")[0]) > 25:
                message_con = self.to_discord_format(message)
                return f"**{message.user.name}**: {message_con}"
            else:
                return ""
        else:
            message_con = self.to_discord_format(message)
            return f"**{message.user.name}**: {message_con}"

    @staticmethod
    def skype_to_discord_image(message: skpy.SkypeMsg) -> tuple:
        sky_file = io.BytesIO(message.fileContent)
        if sky_file.getbuffer().nbytes <= 8388222:
            sky_name = message.file.name
            file_tuple = (sky_file, sky_name)
            return f"From **{message.user.name}**:", file_tuple
        return f"From **{message.user.name}**:\n Can't send picture, 8mb limit, thx discord.", None

    @staticmethod
    def skype_to_discord_file(message: skpy.SkypeMsg) -> tuple:
        if int(message.file.size) <= 8388222:
            sky_file = io.BytesIO(message.fileContent)
            sky_name = message.file.name
            file_tuple = (sky_file, sky_name)
            return f"From **{message.user.name}**:", file_tuple
        return f"From **{message.user.name}**:\n Can't send file, 8mb limit, thx discord.", None

    # TODO WebSkype quote emojis broken
    # TODO Uniform time appearance
    @staticmethod
    def skype_to_discord_quote(message) -> str:
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

    def to_discord_format(self, message: skpy.SkypeMsg) -> str:
        msg_content = self.markup(message)
        if "</quote>" in msg_content:
            msg_content = self.skype_to_discord_quote(msg_content)

        if "~" in msg_content:
            msg_content = msg_content.replace("~(", " ~(").replace(")~", ")~ ")
            line_splits = msg_content.split('\n')
            for li, line in enumerate(line_splits):
                words_split = line.split(" ")
                for index, sky_msg in enumerate(words_split):
                    emoji = re.match(rex["~.*?~"], sky_msg)
                    if emoji:
                        if emoji.group() in config.emoji:
                            emoji = config.emoji[emoji.group()].split("|")[0]
                            words_split[index] = f":{emoji}:"
                        else:
                            logging.warning(f"Missing Emoji {emoji.group()} in emoji.json.")
                line_splits[li] = " ".join(words_split)
            msg_content = "\n".join(line_splits)

        return msg_content
