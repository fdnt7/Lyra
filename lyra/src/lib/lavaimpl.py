import enum as e
import random as rd
import typing as t
import logging
import contextlib as ctxlib

import yaml
import attr as a
import hikari as hk
import lavasnek_rs as lv


from .errors import NotConnected, QueueEmpty
from .utils import EmojiRefs, GuildConfig, GuildOrInferable, infer_guild, get_client
from .extras import get_img_pallete, get_thumbnail, curr_time_ms, inj_glob


REPEAT_MODES_ALL = 'off|0|one|o|1|all|a|q'.split('|')
REPEAT_EMOJIS: t.Final[list[hk.KnownCustomEmoji]] = []

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


class RepeatMode(e.Enum):
    NONE = 'off'
    ALL = 'all'
    ONE = 'one'


def match_repeat(mode: str) -> RepeatMode:
    if mode in {'off', '0'}:
        return RepeatMode.NONE
    elif mode in {'one', 'o', '1'}:
        return RepeatMode.ONE
    elif mode in {'all', 'a', 'q'}:
        return RepeatMode.ALL
    else:
        raise NotImplementedError


# class QueuePosition(int):
#     def __new__(cls, *args, **kwargs):
#         return super().__new__(cls, *args, **kwargs)

#     def __add__(self, __x: int):
#         return QueuePosition(super().__add__(__x))


@a.s(auto_attribs=False, auto_detect=True)
class QueueList(list[lv.TrackQueue]):
    pos: int = 0
    repeat_mode: RepeatMode = RepeatMode.NONE
    is_paused: bool = a.field(factory=bool, kw_only=True)
    is_stopped: bool = a.field(factory=bool, kw_only=True)
    _paused_np_position: t.Optional[int] = a.field(default=None, init=False)
    _curr_t_started: int = a.field(factory=curr_time_ms, init=False)

    def __repr__(self) -> str:
        return "[\n\t%s\n]" % '\n\t'.join(
            f'{i} {t.track.info.title}{" <<" if i == self.pos else ""}'
            for i, t in enumerate(self)
        )

    @classmethod
    def from_seq(cls, l: t.Sequence[lv.TrackQueue]):
        obj = cls()
        obj.extend(l)
        return obj

    @property
    def np_position(self) -> t.Optional[int]:
        if self.is_paused:
            return self._paused_np_position
        if not self.current:
            return None

        return curr_time_ms() - self._curr_t_started

    @property
    def current(self) -> t.Optional[lv.TrackQueue]:
        if not self:
            raise QueueEmpty

        if self.pos <= len(self) - 1:
            return self[self.pos]

        return None

    @property
    def playing(self) -> bool:
        return not (self.is_paused or self.is_stopped) and bool(self.current)

    @property
    def upcoming(self) -> list[lv.TrackQueue]:
        if not self:
            raise QueueEmpty

        return self[self.pos + 1 :]

    @property
    def history(self) -> list[lv.TrackQueue]:
        if not self:
            raise QueueEmpty

        return self[: self.pos]

    @property
    def length(self) -> int:
        return len(self)

    def ext(self, *tracks: lv.TrackQueue) -> None:
        self.extend(tracks)

    def sub(self, *tracks: lv.TrackQueue) -> None:
        for t in tracks:
            self.remove(t)

    def adv(self) -> None:
        self.pos += 1

    def wrap(self) -> None:
        self.pos %= len(self)

    def decr(self) -> None:
        self.pos -= 1

    @property
    def next(self) -> t.Optional[lv.TrackQueue]:
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

    def shuffle(self) -> None:
        if not self:
            raise QueueEmpty

        upcoming = self.upcoming
        rd.shuffle(upcoming)
        hist = self[: self.pos + 1]
        self.clear()
        self.extend(hist + upcoming)

    def set_repeat(self, mode: str) -> RepeatMode:
        self.repeat_mode = (m := match_repeat(mode))
        return m

    def clr(self) -> None:
        self.clear()
        self.reset_repeat()
        self.pos = 0

    def reset_repeat(self) -> None:
        if self.repeat_mode is RepeatMode.ONE or self.repeat_mode is RepeatMode.ALL:
            self.repeat_mode = RepeatMode.NONE if len(self) == 1 else RepeatMode.ALL

    def update_curr_t_started(self, delta_ms: int = 0):
        self._curr_t_started = curr_time_ms() + delta_ms

    @property
    def curr_t_palette(self):
        url = self.curr_t_thumbnail
        c = get_img_pallete(url)
        return c

    @property
    def curr_t_thumbnail(self):
        np = self.current
        assert np
        return get_thumbnail(np.track.info)


@a.s(frozen=True, auto_attribs=False, auto_detect=True)
class Bands(tuple[float]):
    name: t.Optional[str] = a.field(default=None, kw_only=True)
    key_: t.Optional[str] = a.field(default=None, kw_only=True)

    __loaded_bands: t.ClassVar[JSONBands] = {}
    __cached_bands: t.ClassVar[dict[str, 'Bands']] = {}

    @property
    def key(self) -> t.Optional[str]:
        if self.key_ is None:
            return getattr(self.name, 'lower', lambda: None)()
        return self.key_

    @classmethod
    def _load_bands(cls) -> JSONBands:
        fn = next(inj_glob('./bands.yml'))
        with open(fn.resolve(), 'r') as f:
            data = yaml.load(f, yaml.Loader)  # type: ignore
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

        bands = loaded[key]['bands']
        name = loaded[key]['name']

        assert isinstance(bands, list) and isinstance(name, str)

        obj = super().__new__(cls, bands)
        obj.__init__(name=name, key_=key)
        cls.__cached_bands[key] = obj
        return obj


Bandsish = Bands | BandsishTuple


@a.define
class Equalizer(object):
    is_muted: bool = a.field(factory=bool, kw_only=True)
    bands: Bandsish = a.field(factory=Bands.none)
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
    out_channel_id: t.Optional[hk.Snowflakeish] = a.field(default=None, init=False)

    _nowplaying_msg: t.Optional[hk.Message] = a.field(default=None, init=False)
    _nowplaying_components: t.Optional[t.Sequence[hk.api.ActionRowBuilder]] = a.field(
        default=None, init=False
    )
    _track_stopped_fired: bool = a.field(factory=bool, init=False)
    _dc_on_purpose: bool = a.field(factory=bool, init=False)
    ...


loggerX = logging.getLogger(__name__)
loggerX.setLevel(logging.DEBUG)


class EventHandler:
    async def track_start(
        self,
        lvc: lv.Lavalink,
        event: lv.TrackStart,
        /,
    ) -> None:
        t = (await lvc.decode_track(event.track)).title

        if not await lvc.get_guild_node(event.guild_id):
            return
        async with access_data(event.guild_id, lvc) as d:
            q = d.queue
            l = len(d.queue)
            if q.is_stopped:
                return
            q.update_curr_t_started()
            loggerX.debug(
                f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] started: '{t}'"
            )

            client = get_client()

            cfg = client.get_type_dependency(GuildConfig)
            erf = client.get_type_dependency(EmojiRefs)

            assert cfg and erf

            from .music import generate_nowplaying_embed__

            if cfg[str(event.guild_id)].setdefault('send_nowplaying_msg', False):
                ch = d.out_channel_id
                assert ch and client.cache
                embed = await generate_nowplaying_embed__(
                    event.guild_id, client.cache, lvc
                )
                controls = client.rest.build_action_row()
                (
                    controls.add_button(hk.ButtonStyle.SECONDARY, 'lyra_shuffle')
                    .set_emoji(erf['shuffle_b'])
                    .add_to_container()
                )
                (
                    controls.add_button(hk.ButtonStyle.SECONDARY, 'lyra_previous')
                    .set_emoji(erf['previous_b'])
                    .add_to_container()
                )
                (
                    controls.add_button(hk.ButtonStyle.PRIMARY, 'lyra_playpause')
                    .set_emoji(erf['resume_b'])
                    .add_to_container()
                )
                (
                    controls.add_button(hk.ButtonStyle.SECONDARY, 'lyra_skip')
                    .set_emoji(erf['skip_b'])
                    .add_to_container()
                )
                (
                    controls.add_button(hk.ButtonStyle.SUCCESS, 'lyra_repeat')
                    .set_emoji(get_repeat_emoji(q))
                    .add_to_container()
                )

                d._nowplaying_components = components = (controls,)
                d._nowplaying_msg = await client.rest.create_message(
                    ch, embed=embed, components=components
                )

            # await asyncio.sleep(1)
            # await skip__(event.guild_id, lvc)

    async def track_finish(self, lvc: lv.Lavalink, event: lv.TrackFinish, /) -> None:
        if not await lvc.get_guild_node(event.guild_id):
            return
        t = (await lvc.decode_track(event.track)).title
        async with access_data(event.guild_id, lvc) as d:
            q = d.queue
            l = len(q)

            client = get_client()

            cfg = client.get_type_dependency(GuildConfig)
            assert cfg

            if cfg[str(event.guild_id)].get('send_nowplaying_msg', False) and (
                msg := d._nowplaying_msg
            ):
                ch = d.out_channel_id
                assert ch
                try:
                    await client.rest.delete_messages(ch, msg)
                finally:
                    d._nowplaying_msg = d._nowplaying_components = None

            if q.is_stopped:
                loggerX.info(
                    f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] stopped: '{t}'"
                )
                d._track_stopped_fired = True
                return
            try:
                if next_t := q.next:
                    await lvc.play(event.guild_id, next_t.track).start()
                rep = q.repeat_mode
                if rep is RepeatMode.ALL:
                    q.adv()
                    q.wrap()
                elif rep is RepeatMode.NONE:
                    q.adv()
            except QueueEmpty:
                return
            finally:
                loggerX.debug(
                    f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] ended  : '{t}'"
                )
                # d._track_finished_fired = True

    async def track_exception(
        self, lvc: lv.Lavalink, event: lv.TrackException, /
    ) -> None:
        t = (await lvc.decode_track(event.track)).title
        q = await get_queue(event.guild_id, lvc)
        l = len(q)

        msg = f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] {{0}}: '{t}'\n\t{event.exception_message}\n\tCaused by: {event.exception_cause}"

        exc_sev = event.exception_severity
        if exc_sev == 'COMMON':
            loggerX.warning(msg.format('inaccessible'))
        elif exc_sev == 'SUSPICIOUS':
            loggerX.error(msg.format('malformed'))
        elif exc_sev == 'FAULT':
            loggerX.critical(msg.format('corrupted'))
        else:
            raise NotImplementedError

        from .music import skip__

        await skip__(
            event.guild_id,
            lvc,
            advance=not q.is_stopped,
        )

        client = get_client()

        if not await lvc.get_guild_node(event.guild_id):
            return
        async with access_data(event.guild_id, lvc) as d:
            ch = d.out_channel_id
            msg = d._nowplaying_msg
            assert ch and msg
            try:
                await client.rest.delete_messages(ch, msg)
            finally:
                d._nowplaying_msg = d._nowplaying_components = None
            ch = d.out_channel_id
            assert ch
            await client.rest.create_message(
                ch, f"⁉️⏭️ ~~`{t}`~~ `(Error playing this track)`"
            )


async def get_data(guild: hk.Snowflakeish, lvc: lv.Lavalink, /) -> NodeData:
    node = await lvc.get_guild_node(guild)
    if not node:
        raise NotConnected
    data = node.get_data() or NodeData()
    assert isinstance(data, NodeData)
    return data


async def set_data(guild: hk.Snowflakeish, lvc: lv.Lavalink, data: NodeData, /) -> None:
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


async def get_queue(g_inf: GuildOrInferable, lvc: lv.Lavalink, /) -> QueueList:
    return (await get_data(infer_guild(g_inf), lvc)).queue


async def edit_now_playing_components(
    rest: hk.api.RESTClient,
    data: NodeData,
    components: tuple[hk.api.ComponentBuilder],
    /,
):
    if _np_msg := data._nowplaying_msg:
        assert _np_msg and components and data.out_channel_id
        await rest.edit_message(data.out_channel_id, _np_msg, components=components)


def get_repeat_emoji(q: QueueList, /):
    return (
        REPEAT_EMOJIS[0]
        if q.repeat_mode is RepeatMode.NONE
        else (REPEAT_EMOJIS[1] if q.repeat_mode is RepeatMode.ALL else REPEAT_EMOJIS[2])
    )
