import sys
import logging
from discord_client import ApplicationDiscord
from skype_client import AsyncSkype
from config import *


if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)


def main():
    load_config()
    logging.info("Start discord run")
    app = ApplicationDiscord()
    skype = AsyncSkype(config.MAIN.skype_email, config.MAIN.skype_password)
    app.skype, skype.discord = skype, app
    app.run(config.MAIN.login_token)


if __name__ == "__main__":
    main()
