from ._imports import *
from .errors import NotConnected, QueueEmpty
from .utils import curr_time_ms, snowflakeify, GuildInferable, Contextish


REPEAT_MODES_ALL = 'off|0|one|o|1|all|a|q'.split('|')

BandsLikeTuple = tuple[
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
'''A tuple containing exactly 15 floats, each element being in between [-0.25, +0.25]'''
JSONBands = dict[str, dict[str, str | list[float]]]


class RepeatMode(e.Enum):
    NONE = 'off'
    ALL = 'all'
    ONE = 'one'


def match_repeat(mode: str) -> RepeatMode:
    match mode:
        case 'off' | '0':
            return RepeatMode.NONE
        case 'one' | 'o' | '1':
            return RepeatMode.ONE
        case 'all' | 'a' | 'q':
            return RepeatMode.ALL
        case _:
            raise NotImplementedError


@a.define
class QueueList(list):
    pos: int = 0
    repeat_mode: RepeatMode = RepeatMode.NONE
    is_paused: bool = a.field(factory=bool, kw_only=True)
    is_stopped: bool = a.field(factory=bool, kw_only=True)
    _paused_np_position: t.Optional[int] = a.field(default=None, init=False)
    _curr_t_started: int = a.field(factory=curr_time_ms, init=False)

    @t.overload
    def __getitem__(self, y: int) -> lv.TrackQueue:
        ...

    @t.overload
    def __getitem__(self, y: slice) -> list[lv.TrackQueue]:
        ...

    def __getitem__(self, y):
        return super().__getitem__(y)

    def __iter__(self) -> t.Iterator[lv.TrackQueue]:
        return super().__iter__()

    def __repr__(self) -> str:
        return "<<\n\t%s\n>>" % '\n\t'.join(
            f'{i} {t.track.info.title}{" <-" if i == self.pos else ""}'
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


@a.s(frozen=True, auto_attribs=False, auto_detect=True)
class Bands(tuple):
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
        with open('src/lib/bands.yaml', 'r') as f:
            data = yaml.load(f, yaml.Loader)
            cls.__loaded_bands = data
            # with open('src/lib/bands.yaml', 'a') as f:
            #     yaml.dump(data, f)
            return data

    @classmethod
    def from_tup(cls, tup: BandsLikeTuple, /, *, name: str):
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

    @t.overload
    def __getitem__(self, y: int) -> float:
        ...

    @t.overload
    def __getitem__(self, y: slice) -> list[float]:
        ...

    def __getitem__(self, y):
        return super().__getitem__(y)

    def __iter__(self) -> t.Iterator[float]:
        return super().__iter__()


Bandsish = Bands | BandsLikeTuple


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
    _track_finished_fired: bool = a.field(factory=bool, init=False)
    ...


loggerX = logging.getLogger(__name__)
loggerX.setLevel(logging.DEBUG)


class EventHandler:
    async def track_start(
        self,
        lvc: lv.Lavalink,
        event: lv.TrackStart,
    ) -> None:
        t = (await lvc.decode_track(event.track)).title

        async with access_data(event.guild_id, lvc) as d:
            q = d.queue
            l = len(d.queue)
            if q.is_stopped:
                return
            q._curr_t_started = curr_time_ms()
            loggerX.debug(
                f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] started: '{t}'"
            )

            from src.client import client, guild_config
            from .music import generate_nowplaying_embed__

            cfg = guild_config.copy()

            if cfg[str(event.guild_id)].setdefault('send_nowplaying_msg', False):
                ch = d.out_channel_id
                assert ch and client.cache
                embed = await generate_nowplaying_embed__(
                    event.guild_id, client.cache, lvc
                )
                controls = client.rest.build_action_row()
                (
                    controls.add_button(hk_msg.ButtonStyle.SECONDARY, 'lyra_shuffle')
                    .set_emoji('🔀')
                    .add_to_container()
                )
                (
                    controls.add_button(hk_msg.ButtonStyle.SECONDARY, 'lyra_previous')
                    .set_emoji('⏮️')
                    .add_to_container()
                )
                (
                    controls.add_button(hk_msg.ButtonStyle.PRIMARY, 'lyra_playpause')
                    .set_emoji('⏸️')
                    .add_to_container()
                )
                (
                    controls.add_button(hk_msg.ButtonStyle.SECONDARY, 'lyra_skip')
                    .set_emoji('⏭️')
                    .add_to_container()
                )
                (
                    controls.add_button(hk_msg.ButtonStyle.SUCCESS, 'lyra_repeat')
                    .set_emoji('➡️')
                    .add_to_container()
                )

                d._nowplaying_components = components = (controls,)
                d._nowplaying_msg = await client.rest.create_message(
                    ch, embed=embed, components=components
                )

            # await asyncio.sleep(1)
            # await skip__(event.guild_id, lvc)

    async def track_finish(self, lvc: lv.Lavalink, event: lv.TrackFinish) -> None:
        t = (await lvc.decode_track(event.track)).title
        async with access_data(event.guild_id, lvc) as d:
            q = d.queue
            l = len(q)

            from src.client import client, guild_config

            cfg = guild_config.copy()

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
                d._track_finished_fired = True
                return
            try:
                if next_t := q.next:
                    await lvc.play(event.guild_id, next_t.track).start()
                match q.repeat_mode:
                    case RepeatMode.ALL:
                        q.adv()
                        q.wrap()
                    case RepeatMode.NONE:
                        q.adv()
                    case RepeatMode.ONE:
                        pass
            except QueueEmpty:
                return
            finally:
                loggerX.debug(
                    f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] ended  : '{t}'"
                )
                d._track_finished_fired = True

    async def track_exception(self, lvc: lv.Lavalink, event: lv.TrackException) -> None:
        t = (await lvc.decode_track(event.track)).title
        q = await get_queue(event.guild_id, lvc)
        l = len(q)

        msg = f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] {{0}}: '{t}'\n\t{event.exception_message}\n\tCaused by: {event.exception_cause}"

        match event.exception_severity:
            case 'COMMON':
                loggerX.warning(msg.format('inaccessible'))
            case 'SUSPICIOUS':
                loggerX.error(msg.format('malformed'))
            case 'FAULT':
                loggerX.critical(msg.format('corrupted'))
            case _:
                raise NotImplementedError

        # If a track was unable to be played, skip it
        from .music import skip__

        await skip__(
            event.guild_id,
            lvc,
            advance=not q.is_stopped,
        )

        from src.client import client

        ch = (await get_data(event.guild_id, lvc)).out_channel_id
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
    assert node is not None
    node.set_data(data)


@ctxlib.asynccontextmanager
async def access_queue(g_inf: GuildInferable, lvc: lv.Lavalink, /):
    g_inf = snowflakeify(g_inf)

    data = await get_data(g_inf, lvc)
    try:
        yield data.queue
    finally:
        await set_data(g_inf, lvc, data)


@ctxlib.asynccontextmanager
async def access_equalizer(g_inf: GuildInferable, lvc: lv.Lavalink, /):
    g_inf = snowflakeify(g_inf)

    data = await get_data(g_inf, lvc)
    try:
        yield data.equalizer
    finally:
        await set_data(g_inf, lvc, data)


@ctxlib.asynccontextmanager
async def access_data(g_inf: GuildInferable, lvc: lv.Lavalink, /):
    g_inf = snowflakeify(g_inf)

    data = await get_data(g_inf, lvc)
    try:
        yield data
    finally:
        await set_data(g_inf, lvc, data)


async def get_queue(g_inf: GuildInferable, lvc: lv.Lavalink, /) -> QueueList:
    g_inf = snowflakeify(g_inf)

    return (await get_data(g_inf, lvc)).queue


async def edit_now_playing_components(
    rest: hk.api.RESTClient,
    data: NodeData,
    components: tuple[hk.api.ComponentBuilder],
    /,
):
    if _np_msg := data._nowplaying_msg:
        assert _np_msg and components and data.out_channel_id
        await rest.edit_message(data.out_channel_id, _np_msg, components=components)
