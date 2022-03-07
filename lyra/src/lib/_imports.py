import re
import os
import io
import time
import json
import enum as e
import math as m
import asyncio
import logging
import random as rd
import typing as t
import pathlib as pl
import difflib as dfflib
import datetime as dt
import requests as rq
import traceback as tb

import functools as ft
import contextlib as ctxlib
import urllib.error as urllib_er
import urllib.request as urllib_rq

import yaml
import attr as a
import scipy.cluster
import hikari as hk
import tanjun as tj
import alluka as al
import aiohttp

# import colorthief as cltf
import lavasnek_rs as lv
import lyricsgenius as lg
import sklearn.cluster

from PIL import Image as pil_img
from ytmusicapi import YTMusic
from hikari.messages import MessageFlag as msgflag
from hikari.messages import ButtonStyle as bttstyle
from hikari.permissions import Permissions as hkperms
