import os
import sys
import json
import logging
import configparser
from argparse import ArgumentParser

PROG_NAME = "skype-bot"
BASE_DIR = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
HOME_DIR = os.path.expanduser("~")
DEFAULT_CONFIG_PATHS = [
    os.path.join(HOME_DIR, ".skype-bot.ini"),
    os.path.join(BASE_DIR, "skype-bot.local.ini"),
    os.path.join("skype-bot.local.ini"),
    os.path.join("/etc/skype-bot.ini"),
    os.path.join(BASE_DIR, "skype-bot.ini"),
    os.path.join("skype-bot.ini"),
]


class ImproperlyConfigured(Exception):
    pass


class bidict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in self.items():
            self[value] = key

    def __setitem__(self, key, value):
        if key in self:
            super().__delitem__(self[key])
        super().__setitem__(key, value)
        super().__setitem__(value, key)

    def __delitem__(self, key):
        super().__delitem__(self[key])
        super().__delitem__(key)


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

    def update(self, *d, **kwargs):
        for key, val in (d[0] if d else kwargs).items():
            setattr(self, key, val)

    def __getattr__(self, item):
        # expected behaviour:
        raise AttributeError(f"{self.__class__.__name__} object has no attribute {item}")

        # what we actually do:
        # return self.setdefault(item, AttrDict())


config = AttrDict()
def load_config():
    p = ArgumentParser(prog=PROG_NAME)
    p.add_argument("--config", default=None)

    args = p.parse_args()

    if args.config and not os.path.isfile(args.config):
        raise Exception("invalid config file.")

    ini_conf = configparser.ConfigParser()
    if args.config:
        ini_conf.read(args.config)
    else:
        for path in DEFAULT_CONFIG_PATHS:
            if os.path.isfile(path):
                ini_conf.read(path)
                break
        else:
            raise ImproperlyConfigured("No configuration file found.")
    for key, val in ini_conf.items():
        if isinstance(val, (dict, configparser.SectionProxy)):
            val = AttrDict(val)
        config[key] = val

    debug = int(config.MAIN.get("debug", 0))
    if debug:
        os.environ["PYTHONASYNCIODEBUG"] = "1"
        # The AIO modules need to be reloaded because of the new env var
        # reload(asyncio)

    if debug >= 3:
        log_level = logging.DEBUG
    elif debug >= 2:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(level=log_level)
    logging.getLogger('').addHandler(logging.FileHandler("output.log"))

    config.ch = bidict()
    for key, channel_id in config.DISCORD_CHANNELS.items():
        config.ch[int(channel_id)] = f"{config.SKYPE_CHANNELS[key]}"
    logging.info(f"Channel:\n{config.ch}")

    config.emoji = bidict()
    with open(BASE_DIR + "/emoji/emoji.json") as emoji_json:
        emoji_dict = json.load(emoji_json)
    for discord_emo, skype_emo in emoji_dict.items():
        config.emoji[discord_emo] = skype_emo

    config.unicode_emoji = {}
    with open(BASE_DIR + "/emoji/unicode_emoji.json") as emoji_json:
        emoji_dict = json.load(emoji_json)
    for unicode, discord_name in emoji_dict.items():
        config.unicode_emoji[unicode] = discord_name

    config.admin_id = []
    for user_id in config.ADMIN_ID.values():
        config.admin_id.append(user_id)
    logging.info(f"Admin:\n{config.admin_id}")


__all__ = ['config', 'load_config', 'bidict']
