# Discord-Skype-Bot
Discord-Bot that connects discord and skype.  

## Work in Progress 

## Usage

1. Start with installing the dependencies with `pip`.
2. Change necessary settings in the config file (`skype-bot.ini`).
3. Get your skype chat-id:
    ```
    $ python skype-get.py
    ```
    You will now find a new file in your config folder.  
4. Start the bot by executing:
    ```
    $ python bot.py
    ```
That’s it.

## Requirements
To run this project, you will need:
- Python 3.6
- SkPy 0.8
- Pip for Python
- Your own set of Discord credentials to use for the bot (see https://discordapp.com/developers/docs/intro)

### Temporary Bridges
You can add/delete a temporary bridge during runtime. Just send a private message to the bot with:  
```
YOUR_PREFIXtemp_bridge add skype:SKYPE_CHAT_ID discord:DISCORD_CHAT_ID
```
or  
```
YOUR_PREFIXtemp_bridge delete skype:SKYPE_CHAT_ID discord:DISCORD_CHAT_ID
```
Example:  
```
<<temp_bridge add skype:19:47ec9ce6assdasdasdasda@thread.skype discord:386899999999
```
## Images
Discord -> Skype

![Message in Discord](https://0x0.st/RTB.png)
![Relayed to Skype](https://0x0.st/RTa.png)

Skype -> Discord

![Message in Skype](https://0x0.st/RTM.png)
![Relayed to Discord](https://0x0.st/RTu.png)

### Thanks  
BluBb_mADe, dark_star90, kageru

### Help?

Add me on discord and message me with your problem:
Infi#8527 