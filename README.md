# Λύρα
A featureful Discord music bot, made with [hikari](https://github.com/hikari-py/hikari), [hikari-tanjun](https://github.com/FasterSpeeding/Tanjun) and [lavasnek_rs](https://github.com/vicky5124/lavasnek_rs) on Python 3.10.2.

## Prerequisites
* Set up a *firebase real-time database*
* Create & fill these files with the necessary info:
    * `.env`
        ```py
        GENIUS_ACCESS_TOKEN="..."
        LYRA_DEV_TOKEN="..." # optional if dev_mode is false
        LYRA_TOKEN="..."

        LAVALINK_HOST="lavalink"
        LAVALINK_PASSWORD="..."
        LAVALINK_PORT="..."

        FIREBASE_KEY_FILE="..."
        FIREBASE_URL="..."
        ```
    * `config.yml`
        ```yml
        dev_mode: false # true/false
        prefixes:
        - '...'
        guilds: # optional if dev_mode is false
        - ...
        ```
* Obtain these files
    * `headers_auth.json` (Instructions [here](https://ytmusicapi.readthedocs.io/en/latest/setup.html))
    * `xxx-firebase-adminsdk-xxx-xxx.json` (Your firebase keys)

## Building & Running the bot via docker
* 
    ```
    docker compose up
    ``` 

    You can also add the `-d` flag to run the containers in detached mode

## Running the bot without docker
If given two options, do the former when running on Windows and latter when running on Linux.
* Create a `lavalink-win` or `lavalink-linux` folder
* Put the `jdk-13.0.2` folder (from [this .zip](https://download.java.net/java/GA/jdk13.0.2/d4173c853231432d94f001e99d882ca7/8/GPL/openjdk-13.0.2_windows-x64_bin.zip) or [this .tar.gz](https://download.java.net/java/GA/jdk13.0.2/d4173c853231432d94f001e99d882ca7/8/GPL/openjdk-13.0.2_linux-x64_bin.tar.gz)) and `application.yml` in there
* Run `scripts/server.bat` or `scripts/server.sh`
* Run `scripts/bot-startup.bat` or `scripts/bot-startup.sh`

## Toggling between dev modes
* 
    ```
    python3 ./lyra/tggldev.py [OPTIONS]
    ```
    Options:
    * `--dev`, `-d`: The dev mode. Possible values are `t | T` for On and `f | F` for Off. If this option was not parsed, the mode will be toggled from the previous state.