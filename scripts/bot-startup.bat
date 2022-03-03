:: For starting the bot with a delay to wait for the lavalink server to starts up first (Windows)

@echo off
echo ... Waiting for the lavalink server to start up
timeout /t 60 /nobreak > NUL && python ..\lyra\tggldev.py -d f && cd ..\lyra && python -O main.py