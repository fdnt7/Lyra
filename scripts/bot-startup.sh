# For starting the bot with a delay to wait for the lavalink server to starts up first (Windows)

echo ... Waiting for the lavalink server to start up
sleep 60
python3 ./lyra/tggldev.py -d f && cd lyra && python3 -O main.py
