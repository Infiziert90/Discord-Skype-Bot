#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2017 Infi

import os
import sys
import asyncio
import logging
from skpy import Skype
from importlib import reload
from argparse import ArgumentParser
from configparser import ConfigParser


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


__version__ = "0.1.0-Alpha"
PROG_NAME = "skype-get"

if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)


class ImproperlyConfigured(Exception):
    pass


def parse_args():
    version = f"{PROG_NAME}: {__version__}"
    p = ArgumentParser(prog=PROG_NAME)
    p.add_argument("--version", action="version", version=version)
    p.add_argument("--config")

    return p.parse_args()


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

config, logger = get_config()

# Make main config area global, since used everywhere/anywhere
MAIN = config['MAIN']

# get skype connection
sk = Skype(MAIN.get("skype_email"), MAIN.get("skype_password"))

# In this __main__ thing so can be used as library.
def main():
    args = parse_args()
    if args.config:
        path_to_file = args.config
    else:
        for path in DEFAULT_CONFIG_PATHS:
            if os.path.isfile(path):
                path_to_file = path
                break
        else:
            raise ImproperlyConfigured("No configuration file found.")

    version = f"{PROG_NAME}: {__version__}\n\n\n"
    skype_chats_recent = []
    for keys, chat in sk.chats.recent().items():
        if chat.__class__.__name__ == "SkypeSingleChat":
            skype_chats_recent.append(f"SkypeSingleChat:\nName = {chat.user.name}\nChat_ID = 8:{chat.user.id}\n\n")
        if chat.__class__.__name__ == "SkypeGroupChat":
            skype_chats_recent.append(f"SkypeGroupChat:\nName = {chat.topic}\nChat_ID = {chat.id}\n\n")
    recent_chats = "".join(skype_chats_recent)
    with open(path_to_file[:-4] + "-information.txt", "w") as skype_info:
        skype_info.writelines(version + recent_chats)


if __name__ == "__main__":
    main()
