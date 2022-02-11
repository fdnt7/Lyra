import typing as t
import aiohttp
import asyncio

from pprint import pprint


async def get_lyrics_ge(song: str):
    async with aiohttp.request(
        'GET', 'https://some-random-api.ml/lyrics?title=' + song, headers={}
    ) as r:
        if not 200 <= r.status <= 299:
            return
        data = await r.json()
        lyrics: str = data['lyrics']

        # if len(data['lyrics']) > 2_000:
        #     links: str = data['links']['genius']
        #     lyrics = f'{wr(lyrics, 1_900)}\n**View full lyrics on:** {links}'

        return data


a = asyncio.run(get_lyrics_ge('Shelter'))
pprint(a)
