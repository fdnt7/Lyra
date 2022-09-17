import abc
import enum as e
import random as rd
import typing as t
import asyncio
import datetime as dt
import contextlib as ctxlib

import yaml
import attr as a
import hikari as hk
import lavasnek_rs as lv

from ..utils import GuildOrInferable, infer_guild, limit_img_size_by_guild
from ..errors import NotConnected, QueueEmpty
from ..consts import STOP_REFRESH
from ..extras import (
    List,
    Option,
    Result,
    Panic,
    RGBTriplet,
    get_img_pallete,
    get_thumbnail,
    curr_time_ms,
    split_preset,
    inj_glob,
    to_stamp,
)


all_repeat_modes: t.Final = split_preset('off|0,one|o|1,all|a|q')
repeat_emojis: t.Final[list[hk.KnownCustomEmoji]] = []

BandsishTuple = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]
"""A tuple containing exactly 15 floats, each element being in between [-0.25, +0.25]"""
JSONBands = dict[str, dict[str, str | list[float]]]
Trackish = lv.Track | lv.Tracks


class RepeatMode(e.Enum):
    NONE = 'off'
    ALL = 'all'
    ONE = 'one'


# class QueuePosition(int):
#     def __new__(cls, *args, **kwargs):
#         return super().__new__(cls, *args, **kwargs)

#     def __add__(self, __x: int):
#         return QueuePosition(super().__add__(__x))


@a.s(auto_attribs=False, auto_detect=True)
class QueueList(List[lv.TrackQueue]):
    pos: int = 0
    repeat_mode: RepeatMode = RepeatMode.NONE
    is_paused: bool = a.field(factory=bool, kw_only=True)
    is_stopped: bool = a.field(factory=bool, kw_only=True)
    _paused_np_position: Option[int] = a.field(default=None, init=False)
    _curr_t_started: int = a.field(factory=curr_time_ms, init=False)

    def __repr__(self) -> str:
        return "[\n\t%s\n]" % '\n\t'.join(
            f'{i} {t.track.info.title}{" <<" if i == self.pos else ""}'
            for i, t in enumerate(self)
        )

    @property
    def np_position(self) -> Option[int]:
        if not self.is_playing:
            return self._paused_np_position
        if not self.current:
            return None

        return curr_time_ms() - self._curr_t_started

    @property
    def current(self) -> Result[Option[lv.TrackQueue]]:
        if not self:
            raise QueueEmpty

        if self.pos <= len(self) - 1:
            return self[self.pos]

        return None

    @property
    def is_playing(self) -> bool:
        return not (self.is_paused or self.is_stopped) and bool(self.current)

    @property
    def upcoming(self) -> Result[list[lv.TrackQueue]]:
        if not self:
            raise QueueEmpty

        return self[self.pos + 1 :]

    @property
    def history(self) -> Result[list[lv.TrackQueue]]:
        if not self:
            raise QueueEmpty

        return self[: self.pos]

    def adv(self) -> None:
        self.pos += 1

    def wrap(self) -> None:
        self.pos %= len(self)

    def decr(self) -> None:
        self.pos -= 1

    @property
    def next(self) -> Result[Option[lv.TrackQueue]]:
        if not self:
            raise QueueEmpty

        pos = self.pos

        if self.repeat_mode is RepeatMode.ONE:
            return self[pos]

        pos += 1

        if pos < 0:
            return None
        elif pos > len(self) - 1:
            if self.repeat_mode is RepeatMode.ALL:
                pos = 0
            else:
                return None

        return self[pos]

    def shuffle(self) -> Result[None]:
        if not self:
            raise QueueEmpty

        upcoming = self.upcoming
        rd.shuffle(upcoming)
        hist = self[: self.pos + 1]
        self.clear()
        self.extend(hist + upcoming)

    def set_repeat(self, mode: RepeatMode) -> None:
        self.repeat_mode = mode

    def clr(self) -> None:
        self.clear()
        self.reset_repeat()
        self.pos = 0

    def reset_repeat(self) -> None:
        if self.repeat_mode is RepeatMode.ONE or self.repeat_mode is RepeatMode.ALL:
            self.repeat_mode = RepeatMode.NONE if len(self) <= 1 else RepeatMode.ALL

    def update_curr_t_started(self, delta_ms: int = 0):
        self._curr_t_started = curr_time_ms() + delta_ms

    def update_paused_np_position(self, value: int = 0):
        self._paused_np_position = value

    @property
    def curr_t_palette(self) -> tuple[RGBTriplet, ...]:
        img = self.curr_t_thumbnail
        if not img:
            return (((0,) * 3),) * 3
        c = get_img_pallete(img)
        return c

    @property
    def curr_t_thumbnail(self):
        np = self.current
        assert np
        return get_thumbnail(np.track.info)


@a.s(frozen=True, auto_attribs=False, auto_detect=True)
class Bands(tuple[float]):
    name: Option[str] = a.field(default=None, kw_only=True)
    key_: Option[str] = a.field(default=None, kw_only=True)

    __loaded_bands: t.ClassVar[JSONBands] = {}
    __cached_bands: t.ClassVar[dict[str, 'Bands']] = {}

    @property
    def key(self) -> Option[str]:
        if self.key_ is None:
            return self.name.lower() if self.name else None
        return self.key_

    @classmethod
    def _load_bands(cls) -> JSONBands:
        fn = next(inj_glob('./bands.yml'))
        with open(fn.resolve(), 'r') as f:
            data = yaml.load(  # pyright: ignore [reportUnknownMemberType]
                f, yaml.Loader
            )
            cls.__loaded_bands = data
            # with open('src/lib/bands.yaml', 'a') as f:
            #     yaml.dump(data, f)
            return data

    @classmethod
    def from_tup(cls, tup: BandsishTuple, /, *, name: str):
        obj = super().__new__(cls, tup)
        obj.__init__(name=name)
        return obj

    @classmethod
    def none(cls):
        return cls.from_tup((0.0,) * 15, name='None')

    flat = none

    @classmethod
    def load(cls, key: str):
        if not cls.__loaded_bands:
            cls._load_bands()

        loaded = cls.__loaded_bands
        if key not in loaded:
            return cls.none()
        if key in (cached := cls.__cached_bands):
            return cached[key]

        bands = t.cast(list[float], loaded[key]['bands'])
        name = t.cast(str, loaded[key]['name'])

        obj = super().__new__(cls, bands)
        obj.__init__(name=name, key_=key)
        cls.__cached_bands[key] = obj
        return obj


Bandsish = Bands | BandsishTuple


@a.define
class Equalizer(object):
    is_muted: bool = a.field(factory=bool, kw_only=True)
    bands: Bands = a.field(factory=Bands.none)
    _volume: int = a.field(default=10, init=False)

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, y: int):
        self._volume = min(max(y, 0), 10)

    def up(self, amount: int = 1):
        self.volume += amount

    def down(self, amount: int = 1):
        self.volume -= amount


@a.define
class NodeData:
    queue: QueueList = a.field(factory=QueueList, init=False)
    equalizer: Equalizer = a.field(factory=Equalizer, init=False)
    out_channel_id: Option[hk.Snowflakeish] = a.field(default=None, init=False)

    nowplaying_msg: Option[hk.Message] = a.field(default=None, init=False)
    nowplaying_components: Option[t.Sequence[hk.api.ActionRowBuilder]] = a.field(
        default=None, init=False
    )
    ...

    async def edit_now_playing_components(
        self,
        rest: hk.api.RESTClient,
        components: tuple[hk.api.ComponentBuilder],
        /,
    ):
        if _np_msg := self.nowplaying_msg:
            assert _np_msg and components and self.out_channel_id
            await rest.edit_message(self.out_channel_id, _np_msg, components=components)


class BaseEventHandler(abc.ABC):
    @abc.abstractmethod
    async def track_start(
        self,
        lvc: lv.Lavalink,
        event: lv.TrackStart,
        /,
    ) -> Panic[None]:
        ...

    @abc.abstractmethod
    async def track_finish(
        self, lvc: lv.Lavalink, event: lv.TrackFinish, /
    ) -> Panic[None]:
        ...

    @abc.abstractmethod
    async def track_exception(
        self, lvc: lv.Lavalink, event: lv.TrackException, /
    ) -> Panic[None]:
        ...


async def get_data(guild: hk.Snowflakeish, lvc: lv.Lavalink, /) -> Panic[NodeData]:
    node = await lvc.get_guild_node(guild)
    if not node:
        raise NotConnected
    data = t.cast(NodeData, node.get_data() or NodeData())
    return data


async def set_data(
    guild: hk.Snowflakeish, lvc: lv.Lavalink, data: NodeData, /
) -> Panic[None]:
    node = await lvc.get_guild_node(guild)
    if not node:
        raise NotConnected
    node.set_data(data)


@ctxlib.asynccontextmanager
async def access_queue(g_inf: GuildOrInferable, lvc: lv.Lavalink, /):
    data = await get_data(g := infer_guild(g_inf), lvc)
    try:
        yield data.queue
    finally:
        await set_data(g, lvc, data)


@ctxlib.asynccontextmanager
async def access_equalizer(g_inf: GuildOrInferable, lvc: lv.Lavalink, /):
    data = await get_data(g := infer_guild(g_inf), lvc)
    try:
        yield data.equalizer
    finally:
        await set_data(g, lvc, data)


@ctxlib.asynccontextmanager
async def access_data(g_inf: GuildOrInferable, lvc: lv.Lavalink, /):
    data = await get_data(g := infer_guild(g_inf), lvc)
    try:
        yield data
    finally:
        await set_data(g, lvc, data)


async def get_queue(g_inf: GuildOrInferable, lvc: lv.Lavalink, /) -> Panic[QueueList]:
    return (await get_data(infer_guild(g_inf), lvc)).queue


def get_repeat_emoji(q: QueueList, /):
    return (
        repeat_emojis[0]
        if q.repeat_mode is RepeatMode.NONE
        else (repeat_emojis[1] if q.repeat_mode is RepeatMode.ALL else repeat_emojis[2])
    )


async def generate_nowplaying_embed(
    guild_id: hk.Snowflakeish, cache: hk.api.Cache, lvc: lv.Lavalink, /
):
    q = await get_queue(guild_id, lvc)
    # e = '⏹️' if q.is_stopped else ('▶️' if q.is_paused else '⏸️')

    curr_t = q.current
    assert curr_t

    t_info = curr_t.track.info
    req = cache.get_member(guild_id, curr_t.requester)
    # print(curr_t.requester)
    assert req, "That member has left the guild"

    song_len = to_stamp(t_info.length)
    # np_pos = q.np_position // 1_000
    # now = int(time.time())

    if thumb := q.curr_t_thumbnail:
        thumb = limit_img_size_by_guild(thumb, guild_id, cache)
    embed = (
        hk.Embed(
            title=f"🎧 __**`#{q.pos + 1}`**__  {t_info.title}",
            description=f'👤 **{t_info.author}** ({song_len})',
            url=t_info.uri,
            color=q.curr_t_palette[0],
            timestamp=dt.datetime.now().astimezone(),
        )
        .set_author(name="Currently playing")
        .set_footer(
            f"📨 {req.display_name}",
            icon=req.display_avatar_url,
        )
        .set_thumbnail(thumb)
    )
    return embed


async def wait_until_current_track_valid(g_inf: GuildOrInferable, lvc: lv.Lavalink, /):
    while True:
        d = await get_data(infer_guild(g_inf), lvc)
        if d.queue.current and d.out_channel_id:
            return
        await asyncio.sleep(STOP_REFRESH)
