# Λύρα
A general-purpose Discord music bot, made with [hikari](https://github.com/hikari-py/hikari), [hikari-tanjun](https://github.com/FasterSpeeding/Tanjun) and [lavasnek_rs](https://github.com/vicky5124/lavasnek_rs) on Python 3.10.2.

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
* Just do 
    ```
    docker compose up
    ``` 

    You can also add the `-d` flag to run the containers in detached mode