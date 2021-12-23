import os

from src import bot


if __name__ == "__main__":
    if os.name != "nt":
        import uvloop

        uvloop.install()

    bot.run()
