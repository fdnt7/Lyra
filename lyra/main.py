import os
import dotenv

# pyright: reportUnknownMemberType=false
dotenv.load_dotenv('../.env')

from src import bot, activity


if __name__ == '__main__':
    if os.name != 'nt':
        import uvloop

        uvloop.install()

    bot.run(activity=activity)
