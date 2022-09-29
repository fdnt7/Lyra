import os
import re
import typing as t
import asyncio

# pyright: reportMissingTypeStubs=false
import sclib as sc
import lyricsgenius as lg

from ytmusicapi import YTMusic


ytm_api: t.Final = YTMusic()
sc_api: t.Final = sc.SoundcloudAPI(os.environ['SOUNDCLOUD_CLIENT_ID'])
gn_api: t.Final = lg.Genius(
    os.environ['GENIUS_ACCESS_TOKEN'], remove_section_headers=True, retries=3, timeout=8
)
gn_api.verbose = False
loop = asyncio.get_event_loop()


time_regex: t.Final = re.compile(
    r"^((\d+):)?([0-5][0-9]|[0-9]):([0-5][0-9]|[0-9])(.([0-9]{1,3}))?$"
)
time_regex_2: t.Final = re.compile(
    r"^(?!\s*$)((\d+)h)?(([0-9]|[0-5][0-9])m)?(([0-9]|[0-5][0-9])s)?(([0-9]|[0-9][0-9]|[0-9][0-9][0-9])ms)?$"
)
youtube_regex: t.Final = re.compile(
    r"^(?:https?:)?(?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]{7,15})(?:[\?&][a-zA-Z0-9\_-]+=[a-zA-Z0-9\_-]+)*(?:[&\/\#].*)?$"
)
soundcloud_regex: t.Final = re.compile(
    r"^(https?:\/\/)?(www.)?(m\.)?soundcloud\.com\/[\w\-\.]+(\/)+[\w\-\.]+/?$"
)
url_regex: t.Final = re.compile(
    r'^(?:http|ftp)s?://'  ## http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  ## domain...
    r'localhost|'  ## localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  ## ...or ip
    r'(?::\d+)?'  ## optional port
    r'(?:/?|[/?]\S+)$',
    re.I,
)
genius_regex: t.Final = re.compile(r'\d*Embed')
genius_regex_2: t.Final = re.compile(r'^.+ Lyrics\n')
# LYRICS_URL = 'https://some-random-api.ml/lyrics?title='
