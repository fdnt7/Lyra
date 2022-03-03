import yaml
import argparse

from colorama import Back as cb
from colorama import Fore as cf
from colorama import Style as cs

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--dev')

args = parser.parse_args()
with open('../config.yml', 'r') as f:
    _y = yaml.load(f, yaml.Loader)

    if args.dev in {'t', 'T'}:
        dev = True
    elif args.dev in {'f', 'F'}:
        dev = False
    elif args.dev == None:
        dev = not _y['dev_mode']
    else:
        raise TypeError("--dev argument must be either t or f")

with open('../config.yml', 'w') as f:
    _y['dev_mode'] = dev
    yaml.dump(_y, f)
    print(
        f"{cs.BRIGHT}tggldev.py{cs.NORMAL}: Changed the bot\'s development mode to {cf.GREEN if dev else cf.RED}{cs.BRIGHT}{dev}{cs.RESET_ALL}"
        f"\n..."
    )
