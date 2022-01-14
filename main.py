import os
import hikari as hk

from src import bot


if __name__ == "__main__":
    if os.name != "nt":
        import uvloop

        uvloop.install()

    bot.run(activity=hk.Activity(name='/play', type=hk.ActivityType.LISTENING))
