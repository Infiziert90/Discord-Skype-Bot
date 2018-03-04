import sys
import logging
from discord_client import ApplicationDiscord
from skpy import SkypeAuthException
from skype_client import AsyncSkype
from config import *


if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)


def main():
    load_config()
    app = ApplicationDiscord()
    try:
        skype = AsyncSkype(config.MAIN.skype_email, config.MAIN.skype_password)
    except SkypeAuthException as err:
        logging.error(f"Can't login into skype.\n{err}")
        exit(1)

    app.skype, skype.discord = skype, app
    try:
        app.run(config.MAIN.login_token)
    except KeyboardInterrupt:
        app.loop_task.close()
        skype.loop_task.close()


if __name__ == "__main__":
    main()
