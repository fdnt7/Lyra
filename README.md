<div align="center">
   
# Λύρα

![Lyra](https://imgur.com/CmEu7bi.png)

[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://pypi.org/project/black)
[![License](https://img.shields.io/github/license/Fridenity/Lyra)](https://github.com/Fridenity/Lyra/blob/main/LICENSE)
  
A featureful Discord music bot, made with [hikari](https://github.com/hikari-py/hikari), [hikari-tanjun](https://github.com/FasterSpeeding/Tanjun) and [lavasnek_rs](https://github.com/vicky5124/lavasnek_rs) on Python 3.10.5.

</div>

## Inviting the bot to your own servers
* DM me on Discord: `Teammìe#0118`. **I am likely to decline your request if your server has a very active VC (`≳6` hr/d)**

## Supporting the bot
* **Please consider supporting the bot by pressing the `❤️ Sponsor` button at the top!**

## Running your own instance of Lýra
### Prerequisites
* Set up a [MongoDB Atlas Database](https://www.mongodb.com/atlas/database)
* Create & fill these files with the necessary info:
    * `.env`
        ```py
        GENIUS_ACCESS_TOKEN="..."
        LYRA_DEV_TOKEN="..." # unused if dev_mode is false
        LYRA_TOKEN="..."

        LAVALINK_HOST="lavalink"
        LAVALINK_PWD="..."
        LAVALINK_PORT="..."

        MONGODB_PWD="..."
        MONGODB_CONN_STR="..." # replace the pwd in the str with %s
        ```
    * `config.yml`
        ```yml
        dev_mode: false # true/false
        prefixes:
        - '...'
        emoji_guild: 777069316247126036 # do not change this
        guilds: # unused if dev_mode is false
        - ...
        ```
* Obtain these files
    * `headers_auth.json` (Instructions [here](https://ytmusicapi.readthedocs.io/en/latest/setup.html))

<sup>**`?`** Feel free to change internal constant and configs in [`lyra/src/lib/consts.py`](lyra/src/lib/consts.py) and add your own EQ bands in [`bands.yml`](bands.yml) </sup>

### Building & Running the bot via docker
*   Run `sudo docker-compose up`

    <sup>**`^`** You can also add the `-d` flag to run the containers in detached mode</sup>

### Running the bot without docker
* In the `lavalink-local` folder

    <sup>**`∨`** Options for *Windows* and *Linux* are superscripted with `win` and `nix` respectively</sup>
    * Extract *(or symlink)* the `jdk-13.0.2`<sup>[win](https://download.java.net/java/GA/jdk13.0.2/d4173c853231432d94f001e99d882ca7/8/GPL/openjdk-13.0.2_windows-x64_bin.zip) | [nix](https://download.java.net/java/GA/jdk13.0.2/d4173c853231432d94f001e99d882ca7/8/GPL/openjdk-13.0.2_linux-x64_bin.tar.gz)</sup> folder
    * Get the latest build of [`Lavalink.jar`](https://ci.fredboat.com/repository/download/Lavalink_Build/9447:id/Lavalink.jar)

    <sub>**`∨`** Your `lavalink-local` folder should look like this</sub>
    
    ```hs
    lavalink-local
    ├──jdk-13.0.2 -- maybe symlink
    │  └──...
    ├──application.yml.dev -- lavalink config, feel free to edit
    └──Lavalink.jar
    ```
        
* Run `(cd lyra && pip install -Ur requirements.txt)`

    <sup>**`^`** If that doesn't work, try `pip3` instead</sup>
    
    <sup>**`^`** If you prefer having a [venv](https://docs.python.org/3/tutorial/venv.html), run `(cd lyra && python -m venv .venv && . lyra/.venv/bin/Activate.ps1 && pip install -Ur requirements.txt)`ʷᶦⁿ | `(cd lyra && python -m venv .venv && . lyra/.venv/bin/activate && pip install -Ur requirements.txt)`ⁿᶦˣ </sup>
    
    
    
* Run [`scripts/server.bat`](scripts/server.bat)<sup>win</sup> | [`scripts/server`](scripts/server)<sup>nix</sup> and wait for Lavalink to finish starting up
* Run [`scripts/bot.bat`](scripts/bot.bat)<sup>win</sup> |  [`scripts/bot`](scripts/bot)<sup>nix</sup> to start the bot up

    <sup>**`^`** To run the bot in debug mode, run [`scripts/bot-debug.bat`](scripts/bot-debug.bat)ʷᶦⁿ | [`scripts/bot-debug`](scripts/bot-debug)ⁿᶦˣ</sup>

### Development
*   Run `pip install -r dev_requirements.txt`
*   Run `scripts/tggldev [OPTIONS]...` to toggle between dev modes

    #### Options:
    * `--dev`, `-d`: The dev mode. Possible values are `t | T` for On and `f | F` for Off. If this option was not given, the mode will be toggled from the previous state.
