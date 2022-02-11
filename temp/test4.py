import os
import lyricsgenius as lg

from pprint import pprint

genius = lg.Genius(os.environ['GENIUS_ACCESS_TOKEN'])


def ge(song: str):
    song_0 = genius.search_song(song)
    if not song_0:
        return

    pprint(song_0.to_dict())
    return song_0.lyrics


pprint(ge("shelter"))
