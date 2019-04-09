import os
import sys
from skpy import Skype
from config import *


if not sys.version_info[:2] >= (3, 6):
    print("Error: requires python 3.6 or newer")
    exit(1)


output_name = os.path.splitext(os.path.basename(__file__))[0]


def main():
    load_config()
    sk = Skype(config.MAIN.skype_email, config.MAIN.skype_password)

    skype_chats_recent = []
    for keys, chat in sk.chats.recent().items():
        if chat.__class__.__name__ == "SkypeSingleChat":
            skype_chats_recent.append(f"SkypeSingleChat:\n\tName = {chat.user.name}\n\tChat_ID = {chat.id}\n\n")
        if chat.__class__.__name__ == "SkypeGroupChat":
            skype_chats_recent.append(f"SkypeGroupChat:\n\tName = {chat.topic}\n\tChat_ID = {chat.id}\n\n")
    recent_chats = "".join(skype_chats_recent)
    print(recent_chats)
    with open(f"{output_name}-information.txt", "w") as skype_info:
        skype_info.writelines(recent_chats)


if __name__ == "__main__":
    main()
