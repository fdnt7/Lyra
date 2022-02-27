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
import difflib as dfflib
import datetime as dt
import requests as rq
import traceback as tb
import contextlib as ctxlib

import attr as a
import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv
import lyricsgenius as lg

from hikari.messages import MessageFlag as msgflag
from hikari.messages import ButtonStyle as bttstyle
from hikari.permissions import Permissions as hkperms
from ytmusicapi import YTMusic
