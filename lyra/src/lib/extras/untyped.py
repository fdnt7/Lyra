import io
import typing as t
import asyncio
import tempfile
import urllib.error as urllib_er
import urllib.request as urllib_rq

# pyright: reportMissingTypeStubs=false
import numpy as np
import scipy.cluster as sp_cls
import sklearn.cluster as sk_cls
import mutagen
import mutagen.flac as mutagen_flac
import memoization as mz
import sclib as sc
import lavasnek_rs as lv

from PIL import Image as pil_img

from .types import Option, OptionFallible, URLstr, RGBTriplet
from .vars import (
    ytm_api,
    gn_api,
    sc_api,
    genius_regex,
    genius_regex_2,
    youtube_regex,
    soundcloud_regex,
)

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false


class LyricsData(t.NamedTuple):
    source: str
    lyrics: str
    title: str
    artist: str
    thumbnail: str
    url: Option[str] = None
    artist_icon: Option[str] = None
    artist_url: Option[str] = None


async def get_lyrics_yt(song: str, /) -> Option[LyricsData]:
    queried = ytm_api.search(song, 'songs') + ytm_api.search(song, 'videos')
    if not queried:
        return None
    track_data_0: str = queried[0]['videoId']
    watches = ytm_api.get_watch_playlist(track_data_0)
    track_data: dict[str, t.Any] = watches['tracks'][0]
    if watches['lyrics'] is None:
        return None

    lyrics_id = t.cast(str, watches['lyrics'])
    lyrics: dict[str, str] = ytm_api.get_lyrics(lyrics_id)
    source: str = lyrics['source'].replace("Source: ", '')

    return LyricsData(
        title=track_data['title'],
        lyrics=lyrics['lyrics'],
        thumbnail=track_data['thumbnail'][-1]['url'],
        artist=" & ".join((a['name'] for a in track_data['artists'])),
        source=source,
    )


async def get_lyrics_ge(song: str, /) -> Option[LyricsData]:
    song_0 = gn_api.search_song(song, get_full_info=False)
    if not song_0:
        return None

    lyrics = gn_api.lyrics(song_url=song_0.url)

    if not lyrics:
        return None

    lyrics = genius_regex_2.sub('', genius_regex.sub('', lyrics))

    artist = song_0.primary_artist
    return LyricsData(
        title=song_0.title,
        url=song_0.url,
        artist=song_0.artist,
        lyrics=lyrics,
        thumbnail=song_0.song_art_image_url,
        source="Genius",
        artist_icon=artist.image_url,
        artist_url=artist.url,
    )


async def get_lyrics(song: str, /) -> dict[str, LyricsData]:
    from ..errors import LyricsNotFound

    # tests = (get_lyrics_ge(song), get_lyrics_yt(song))
    tests = (get_lyrics_yt(song),)
    if not any(lyrics := await asyncio.gather(*tests)):
        raise LyricsNotFound
    return {l.source: l for l in lyrics if l}


@mz.cached
def get_url_audio_album_art(url: URLstr, /) -> Option[bytes]:
    req = urllib_rq.Request(url, headers={'User-Agent': "Magic Browser"})
    with urllib_rq.urlopen(req) as f:
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(f.read())
            file = mutagen.File(tmp.name)
        if isinstance(file, mutagen_flac.FLAC):
            if not file.pictures:
                return None
            return file.pictures[0].data
        if not file:
            return None
        tags = file.tags
        if not tags:
            return None
        if (p := tags.get('APIC:')) or (p := tags.get('APIC:cover')):
            return p.data


@mz.cached
def url_to_bytesio(img_url: URLstr, /) -> io.BytesIO:
    return io.BytesIO(urllib_rq.urlopen(img_url).read())


@mz.cached
def url_to_img(img_url: URLstr, /) -> pil_img.Image:
    return pil_img.open(url_to_bytesio(img_url))


@mz.cached
def img_to_bytes(img: pil_img.Image, /, format: Option[str] = None) -> bytes:
    img.save(b := io.BytesIO(), format)
    return b.getvalue()


@mz.cached
def bytes_to_img(img_b: bytes, /) -> pil_img.Image:
    return pil_img.open(io.BytesIO(img_b))


@mz.cached
def limit_bytes_img_size(img_b: bytes, /, limit_size: int = 8 * 2**20) -> bytes:
    if len(img_b) >= limit_size:
        resize = np.sqrt(len(img_b) / limit_size)
        img = bytes_to_img(img_b)
        return img_to_bytes(
            img.resize((*(int(d / resize) for d in img.size),)), img.format
        )
    return img_b


@mz.cached
def get_img_pallete(
    img_url_b: URLstr | bytes, /, *, n: int = 5, resize: tuple[int, int] = (150, 150)
) -> tuple[RGBTriplet, ...]:
    if isinstance(img_url_b, URLstr):
        img = url_to_img(img_url_b)
    else:
        img = bytes_to_img(img_url_b)
    ## optional, to reduce time
    ar = np.asarray(img.resize(resize))
    shape = ar.shape
    ar = ar.reshape(np.product(shape[:2]), shape[2]).astype(float)

    kmeans = sk_cls.MiniBatchKMeans(
        n_clusters=n, init="k-means++", max_iter=20, random_state=1000
    ).fit(ar)
    codes = kmeans.cluster_centers_

    ## assign codes
    vecs, _ = sp_cls.vq.vq(ar, codes)
    ## count occurrences
    counts, _ = np.histogram(vecs, len(codes))

    return (
        *((*(int(code) for code in codes[i]),) for i in np.argsort(counts)[::-1]),
    )  ## returns colors in order of dominance


@mz.cached
def get_thumbnail(t_info: lv.Info, /) -> OptionFallible[URLstr | bytes]:
    uri = t_info.uri
    id_ = t_info.identifier

    if youtube_regex.fullmatch(uri):
        for x in ('maxresdefault', 'sddefault', 'mqdefault', 'hqdefault', 'default'):
            url = f'https://img.youtube.com/vi/{id_}/{x}.jpg'
            try:
                if (urllib_rq.urlopen(url)).getcode() == 200:
                    return url
            except urllib_er.HTTPError:
                continue
        raise ValueError('Malformed youtube thumbnail uri')
    if soundcloud_regex.fullmatch(uri):
        track = t.cast(sc.Track, sc_api.resolve(uri))
        return track.artwork_url
    return get_url_audio_album_art(uri)
