import re
import os
import time
import json
import yaml
import enum as e
import math as m
import asyncio
import logging
import aiohttp
import random as rd
import typing as t
import hashlib as hl
import requests as rq
import traceback as tb

import attr as a
import hikari as hk
import tanjun as tj
import lavasnek_rs as lv
import hikari.messages as hk_msg
import lyricsgenius as lg

from difflib import SequenceMatcher
from functools import reduce
from contextlib import asynccontextmanager, nullcontext
from ytmusicapi import YTMusic

from hikari.permissions import Permissions as hkperms
from hikari.messages import MessageFlag as msgflag
