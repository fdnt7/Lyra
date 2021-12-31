from .utils import *

STOP_REFRESH = 0.15
DJ_PERMS = P.DEAFEN_MEMBERS | P.MUTE_MEMBERS

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ConnectionSignal(BaseMusicCommandException):
    pass


class InvalidTimestampFormat(BaseMusicCommandException):
    pass


@dataclass
class Forbidden(BaseMusicCommandException):
    perms: P


@dataclass
class ChannelChange(ConnectionSignal):
    old_channel: hk.Snowflakeish
    new_channel: hk.Snowflakeish


class PlaybackException(BaseMusicCommandException):
    pass


@dataclass
class ConnectionException(PlaybackException):
    channel: hk.Snowflakeish


class NotConnected(PlaybackException):
    pass


class AlreadyConnected(ConnectionException):
    pass


class OthersInVoice(ConnectionException):
    pass


class OthersListening(OthersInVoice):
    pass


@dataclass
class NotInVoice(ConnectionException):
    channel: t.Optional[hk.Snowflakeish]


class InternalError(PlaybackException):
    pass


class ConnectionForbidden(ConnectionException, Forbidden):
    pass


@dataclass
class PlaybackChangeRefused(PlaybackException):
    track: t.Optional[lv.TrackQueue] = None


class NotPlaying(PlaybackException):
    pass


class QueueIsEmpty(PlaybackException):
    pass


class TrackPaused(PlaybackException):
    pass


class TrackStopped(PlaybackException):
    pass


class QueryEmpty(BaseMusicCommandException):
    pass


class LyricsNotFound(BaseMusicCommandException):
    pass


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


class LyricsData(t.NamedTuple):
    source: str
    lyrics: t.Optional[str] = None
    title: t.Optional[str] = None
    author: t.Optional[str] = None
    link: t.Optional[str] = None
    thumbnail: t.Optional[str] = None


async def get_lyrics_yt(song: str) -> t.Optional[LyricsData]:
    queried = ytmusic.search(song, 'songs') + ytmusic.search(song, 'videos')
    if not queried:
        return
    track_data_0 = queried[0]['videoId']
    watches = ytmusic.get_watch_playlist(track_data_0)
    track_data = watches['tracks'][0]
    if watches['lyrics'] is None:
        return
    lyrics_id = watches['lyrics']
    assert isinstance(lyrics_id, str)
    return LyricsData(
        title=track_data['title'],
        lyrics=(lyrics := ytmusic.get_lyrics(lyrics_id))['lyrics'],
        thumbnail=track_data['thumbnail'][-1]['url'],
        author=' & '.join((a['name'] for a in track_data['artists'])),
        source=lyrics['source'],
    )


async def get_lyrics_ge(song: str) -> t.Optional[LyricsData]:
    async with aiohttp.request('GET', LYRICS_URL + song, headers={}) as r:
        if not 200 <= r.status <= 299:
            return
        data = await r.json()

        if len(data['lyrics']) > 2000:
            return LyricsData(link=data['links']['genius'], source='Source: Genius')

        return LyricsData(
            title=data['title'],
            lyrics=data['lyrics'],
            thumbnail=data['thumbnail']['genius'],
            author=data['author'],
            source='Source: Genius',
        )


async def get_lyrics(song: str) -> LyricsData:
    tests = (get_lyrics_ge, get_lyrics_yt)
    for T_ in tests:
        if not (lyrics := await T_(song)):
            continue
        return lyrics
    raise LyricsNotFound


class Checks(e.Flag):
    CATCH_ALL = 0

    IN_VC = e.auto()
    """
    Checks whether you are in voice or whether you have the permissions specified
    """

    OTHERS_NOT_IN_VC = e.auto()
    """
    Checks whether there is no one else in voice or whether you have the premissions specified
    """

    IN_VC_ALONE = IN_VC | OTHERS_NOT_IN_VC
    """
    Checks whether you are alone in voice or whether you have the permissions specified
    """

    CONN = e.auto()
    """
    Check whether the bot is currently connected in this guild's voice
    """

    QUEUE = e.auto()
    """
    Check whether the queue for this guild is not yet empty
    """

    PLAYING = e.auto()
    """
    Check whether there is a currently playing track
    """

    CAN_SEEK_QUEUE = e.auto()
    """
    Checks whether your requested track is currently playing or you have the DJ permissions
    """

    ALONE_OR_CAN_SEEK_QUEUE = CAN_SEEK_QUEUE | IN_VC_ALONE
    """
    Checks whether you are alone in voice or whether you have the permissions specified, then checks whether your requested track is currently playing or you have the DJ permissions
    """

    CURR_T_YOURS = e.auto()
    """
    Checks whether you requested the current track or you have the DJ permissions
    """

    ALONE_OR_CURR_T_YOURS = CURR_T_YOURS | IN_VC_ALONE
    """
    Checks whether you are alone in voice or whether you have the permissions specified, then checks whether you requested the current track or you have the DJ permissions
    """

    ADVANCE = STOP = e.auto()
    """
    Check whether the current track had been stopped
    """

    PLAYBACK = PAUSE = e.auto()
    """
    Checks whether the currently playing track had been paused
    """


@dataclass
class QueueList(list):
    pos: int = 0
    repeat_mode: RepeatMode = RepeatMode.NONE
    is_paused: bool = field(default_factory=bool, kw_only=True)
    is_stopped: bool = field(default_factory=bool, kw_only=True)
    _last_np_position: t.Optional[int] = field(default=None, init=False)
    _last_track_played: int = field(default_factory=curr_time_ms, init=False)

    @t.overload
    def __getitem__(self, y: int) -> lv.TrackQueue:
        ...

    @t.overload
    def __getitem__(self, y: slice) -> list[lv.TrackQueue]:
        ...

    def __getitem__(self, y):
        return super().__getitem__(y)

    @classmethod
    def from_list(cls, l: list):
        obj = cls()
        obj.extend(l)
        return obj

    @property
    def np_position(self) -> t.Optional[int]:
        if self.is_paused:
            return self._last_np_position
        if not self.current:
            return None

        return curr_time_ms() - self._last_track_played

    @property
    def current(self) -> t.Optional[lv.TrackQueue]:
        if not self:
            raise QueueIsEmpty

        if self.pos <= len(self) - 1:
            return self[self.pos]

        return None

    @property
    def playing(self) -> bool:
        return not (self.is_paused or self.is_stopped) and bool(self.current)

    @property
    def upcoming(self) -> list[lv.TrackQueue]:
        if not self:
            raise QueueIsEmpty

        return self[self.pos + 1 :]

    @property
    def history(self) -> list[lv.TrackQueue]:
        if not self:
            raise QueueIsEmpty

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

    incr = advance = adv

    @property
    def next(self) -> t.Optional[lv.TrackQueue]:
        if not self:
            raise QueueIsEmpty

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
            raise QueueIsEmpty

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
        self.pos = 0


@dataclass
class NodeData:
    queue: QueueList = field(default_factory=QueueList)
    last_channel_id: t.Optional[hk.Snowflakeish] = None
    ...


class EventHandler:
    async def track_start(self, lvc: lv.Lavalink, event: lv.TrackStart) -> None:
        t = (await lvc.decode_track(event.track)).title
        async with access_queue(event.guild_id, lvc) as q:
            q._last_track_played = curr_time_ms()
            logger.debug(
                f"Started track '{t}' in guild {event.guild_id} ({q.pos}+1/{len(q)})"
            )

    async def track_finish(self, lvc: lv.Lavalink, event: lv.TrackFinish) -> None:
        t = (await lvc.decode_track(event.track)).title
        async with access_queue(event.guild_id, lvc) as q:
            if q.is_stopped:
                logger.debug(
                    f"Stopped track '{t}' in guild {event.guild_id} ({q.pos}+1/{len(q)})"
                )
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
            except QueueIsEmpty:
                return
            finally:
                logger.debug(
                    f"Finished track '{t}' in guild {event.guild_id} ({q.pos}+1/{len(q)})"
                )

    async def track_exception(self, lvc: lv.Lavalink, event: lv.TrackException) -> None:
        logger.error(f"Track exception event happened on guild: {event.guild_id}")

        # If a track was unable to be played, skip it
        await skip__(
            event.guild_id,
            lvc,
            advance=not (await get_queue(event.guild_id, lvc)).is_stopped,
        )


async def check_others_not_in_vc__(ctx: tj.abc.Context, perms: P, conn: dict):
    m = ctx.member
    assert not ((ctx.guild_id is None) or (m is None) or (ctx.client.cache is None))
    auth_perms = await tj.utilities.fetch_permissions(
        ctx.client, m, channel=ctx.channel_id
    )

    channel = conn['channel_id']
    voice_states = ctx.client.cache.get_voice_states_view_for_channel(
        ctx.guild_id, channel
    )
    others_in_voice = tuple(
        filter(
            lambda v: not v.member.is_bot and v.member.id != m.id,
            voice_states.values(),
        )
    )

    if not (auth_perms & (perms | P.ADMINISTRATOR)) and others_in_voice:
        raise OthersInVoice(channel)


async def check_others_not_in_vc(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    conn = await lvc.get_guild_gateway_connection_info(ctx.guild_id)
    assert isinstance(conn, dict)
    await check_others_not_in_vc__(ctx, DJ_PERMS, conn)


async def check_auth_in_vc__(ctx: tj.abc.Context, perms: P, conn: dict):
    m = ctx.member
    assert not ((ctx.guild_id is None) or (m is None) or (ctx.client.cache is None))
    auth_perms = await tj.utilities.fetch_permissions(
        ctx.client, m, channel=ctx.channel_id
    )

    channel = conn['channel_id']
    voice_states = ctx.client.cache.get_voice_states_view_for_channel(
        ctx.guild_id, channel
    )
    author_in_voice = tuple(
        filter(
            lambda v: v.member.id == m.id,
            voice_states.values(),
        )
    )

    if not (auth_perms & (perms | P.ADMINISTRATOR)) and not author_in_voice:
        raise NotInVoice(channel)


async def check_auth_in_vc(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    conn = await lvc.get_guild_gateway_connection_info(ctx.guild_id)
    assert isinstance(conn, dict)
    await check_auth_in_vc__(ctx, DJ_PERMS, conn)


async def check_curr_t_perms(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert not (ctx.guild_id is None or ctx.member is None)
    auth_perms = await tj.utilities.fetch_permissions(
        ctx.client, ctx.member, channel=ctx.channel_id
    )
    q = await get_queue(ctx, lvc)
    assert q.current is not None
    if ctx.author.id != q.current.requester and not auth_perms & (
        DJ_PERMS | P.ADMINISTRATOR
    ):
        raise PlaybackChangeRefused(q.current)


async def check_seeking_perms(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert not (ctx.guild_id is None or ctx.member is None)
    auth_perms = await tj.utilities.fetch_permissions(
        ctx.client, ctx.member, channel=ctx.channel_id
    )
    if not (auth_perms & (DJ_PERMS | P.ADMINISTRATOR)):
        if not (np := (await get_queue(ctx, lvc)).current):
            raise Forbidden(DJ_PERMS)
        if ctx.author.id != np.requester:
            raise PlaybackChangeRefused(np)


async def check_advancability(ctx: tj.abc.Context, lvc: lv.Lavalink):

    assert ctx.guild_id is not None
    if (await get_queue(ctx, lvc)).is_stopped:
        raise TrackStopped


async def check_conn(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    conn = await lvc.get_guild_gateway_connection_info(ctx.guild_id)
    if not conn:
        raise NotConnected


async def check_queue(ctx: tj.abc.Context, lvc: lv.Lavalink):
    if not await get_queue(ctx, lvc):
        raise QueueIsEmpty


async def check_playing(ctx: tj.abc.Context, lvc: lv.Lavalink):
    if not (await get_queue(ctx, lvc)).current:
        raise NotPlaying


async def check_paused(ctx: tj.abc.Context, lvc: lv.Lavalink):
    if (await get_queue(ctx, lvc)).is_paused:
        raise TrackPaused


def check(checks: Checks, perms: P = P.NONE):
    def decorator(func: t.Callable[..., t.Coroutine]):
        async def wrapper(ctx: tj.abc.Context, *args: t.Any, lvc: lv.Lavalink):
            assert ctx.member is not None
            if perms:
                auth_perms = await tj.utilities.fetch_permissions(
                    ctx.client, ctx.member, channel=ctx.channel_id
                )
                if not (auth_perms & (perms | P.ADMINISTRATOR)):
                    raise Forbidden(perms)

            try:
                if Checks.CONN & checks:
                    await check_conn(ctx, lvc)
                if Checks.QUEUE & checks:
                    await check_queue(ctx, lvc)
                if Checks.PLAYING & checks:
                    await check_playing(ctx, lvc)
                if Checks.IN_VC & checks:
                    await check_auth_in_vc(ctx, lvc)
                if Checks.OTHERS_NOT_IN_VC & checks:
                    try:
                        await check_others_not_in_vc(ctx, lvc)
                    except OthersInVoice as exc:
                        if Checks.CAN_SEEK_QUEUE & checks:
                            await check_seeking_perms(ctx, lvc)
                        if Checks.CURR_T_YOURS & checks:
                            await check_curr_t_perms(ctx, lvc)
                        if not (Checks.CURR_T_YOURS | Checks.CAN_SEEK_QUEUE) & checks:
                            raise OthersListening(exc.channel) from exc

                if Checks.STOP & checks:
                    await check_advancability(ctx, lvc)
                if Checks.PAUSE & checks:
                    await check_paused(ctx, lvc)

                await func(ctx, *args, lvc=lvc)
            except Forbidden as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 You lack the `{format_flags(exc.perms)}` permissions to use this command",
                )
            except OthersListening as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 You can only do this if you are alone in <#{exc.channel}>.\n **You bypass this by having the `Deafen` & `Mute Members` permissions**",
                )
            except OthersInVoice as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 Someone else is already in <#{exc.channel}>.\n **You bypass this by having the `Move Members` permissions**",
                )
            except NotInVoice as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 Join <#{exc.channel}> first. **You bypass this by having the `Deafen` & `Mute Members` permissions**",
                )
            except NotConnected:
                await err_reply(
                    ctx,
                    content=f"❌ Not currently connected to any channel. Use `/join` or `/play` first",
                )
            except QueueIsEmpty:
                await err_reply(ctx, content="❗ The queue is empty")
            except NotPlaying:
                await err_reply(ctx, content="❗ Nothing is playing at the moment")
            except PlaybackChangeRefused:
                await err_reply(
                    ctx,
                    content=f"🚫 This can only be done by the current song requester\n**You bypass this by having the `Deafen` & `Mute Members` permissions**",
                )
            except TrackPaused:
                await err_reply(ctx, content="❗ The current track is paused")
            except TrackStopped:
                await err_reply(
                    ctx,
                    content="❗ The current track had been stopped. Use `/skip`, `/restart` or `/remove` the current track first",
                )
            except QueryEmpty:
                await err_reply(
                    ctx, content="❓ No tracks found. Please try changing your wording"
                )

        return wrapper

    return decorator


def attempt_to_connect(func: t.Callable[..., t.Coroutine]):
    async def wrapper(ctx: tj.abc.Context, *args: t.Any, lvc: lv.Lavalink):
        assert ctx.guild_id is not None
        conn = await lvc.get_guild_gateway_connection_info(ctx.guild_id)

        if not conn:
            # Join the users voice channel if we are not already connected
            try:
                if not await join__(ctx, None, lvc):
                    return
            except NotInVoice:
                await err_reply(
                    ctx,
                    content=f"❌ Please join a voice channel first. You can also do `/join channel:` `[🔊 ...]`",
                )
                return

        await func(ctx, *args, lvc=lvc)

    return wrapper


# @hooks.with_on_success
# async def on_success(
#     ctx: tj.abc.Context, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
# ) -> None:
#     guild = ctx.guild_id
#     assert guild is not None

#     node = await lvc.get_guild_node(guild)
#     assert node is not None

#     data = await get_data(guild, lvc)
#     data.last_channel_id = ctx.channel_id
#     await set_data(guild, lvc, data)


async def get_data(guild: hk.Snowflakeish, lvc: lv.Lavalink) -> NodeData:
    node = await lvc.get_guild_node(guild)
    if not node:
        raise NotConnected
    data = (await node.get_data()) or NodeData()
    assert isinstance(data, NodeData)
    return data


async def set_data(guild: hk.Snowflakeish, lvc: lv.Lavalink, data: NodeData) -> None:
    node = await lvc.get_guild_node(guild)
    assert node is not None
    await node.set_data(data)


@asynccontextmanager
async def access_queue(ctx_g: tj.abc.Context | hk.Snowflakeish, lvc: lv.Lavalink):
    if isinstance(ctx_g, tj.abc.Context):
        assert ctx_g.guild_id is not None
        ctx_g = ctx_g.guild_id

    data = await get_data(ctx_g, lvc)
    try:
        yield data.queue
    finally:
        await set_data(ctx_g, lvc, data)


async def get_queue(
    ctx_g: tj.abc.Context | hk.Snowflakeish, lvc: lv.Lavalink
) -> QueueList:
    if isinstance(ctx_g, tj.abc.Context):
        assert ctx_g.guild_id is not None
        ctx_g = ctx_g.guild_id
    return (await get_data(ctx_g, lvc)).queue


music_h = tj.AnyHooks()

guild_c = tj.GuildCheck(error_message="❌ Commands can only be used in guild channels")


@music_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    if isinstance(error, lv.NetworkError):
        await ctx.respond("⁉️ A network error has occurred")
        return True

    # error_tb = f"\n```py\n{''.join(tb.format_exception(type(error), value=error, tb=error.__traceback__))}```"
    error_tb = "`%s`" % error

    await ctx.respond(f"⁉️ An error occurred: {error_tb}")
    return False


## Connections


async def join__(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel],
    lvc: lv.Lavalink,
) -> t.Optional[hk.Snowflake]:
    """Joins your voice channel."""
    assert ctx.guild_id is not None

    if ctx.client.cache and ctx.client.shards:
        if channel is None:
            # If user is connected to a voice channel
            if not (
                (
                    voice_state := ctx.client.cache.get_voice_state(
                        ctx.guild_id, ctx.author
                    )
                )
                is None
            ):
                # Join the current voice channel
                target_channel = voice_state.channel_id
            else:
                raise NotInVoice(None)
        else:
            target_channel = channel.id
            # Join the specified voice channel

        old_conn = await lvc.get_guild_gateway_connection_info(ctx.guild_id)
        assert isinstance(old_conn, dict) or old_conn is None
        assert target_channel is not None

        # Check if the bot is already connected and the user tries to change
        if old_conn:

            old_channel = old_conn['channel_id']
            assert old_channel is not None
            # If it's the same channel
            if old_channel == target_channel:
                raise AlreadyConnected(old_channel)

            await check_others_not_in_vc__(ctx, P.MOVE_MEMBERS, old_conn)
        else:
            old_channel = None

        # Connect to the channel
        await ctx.client.shards.update_voice_state(
            ctx.guild_id, target_channel, self_deaf=True
        )

        # Lavasnek waits for the data on the event
        try:
            sess_conn = await lvc.wait_for_full_connection_info_insert(ctx.guild_id)
        except TimeoutError:
            await def_reply(
                ctx,
                content="⏳ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
            )
            return
        # Lavasnek tells lavalink to connect
        await lvc.create_session(sess_conn)

        """
        TODO Make the bot raise `AccessDenied` if nothing happens after joining a new channel
        """

        # bot = ctx.client.cache.get_me()
        # new_voice_states = ctx.client.cache.get_voice_states_view_for_guild(ctx.guild_id)
        # bot_voice_state = filter(lambda v: v.user_id == bot.id, new_voice_states.values())
        # new_channel = getattr(next(bot_voice_state, None), 'channel_id', None)

        # if new_channel != target_channel:
        #     raise AccessDenied(target_channel)

        # if conn:
        #     voice_states_after = ctx.client.cache.get_voice_states_view_for_channel(
        #         ctx.guild_id, old_channel
        #     )
        #     bot_voice_state = tuple(filter(lambda v: v.user_id == bot.id, voice_states_after.values()))
        #     if bot_voice_state:
        #         raise AccessDenied(target_channel)
        if old_conn and old_channel:
            raise ChannelChange(old_channel, target_channel)

        return target_channel

    raise InternalError


## Playback


async def stop__(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        q.is_stopped = True

    await lvc.stop(ctx.guild_id)  # Stop the player


async def continue__(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        q.is_stopped = False


@asynccontextmanager
async def while_stop(ctx: tj.abc.Context, lvc: lv.Lavalink, q: QueueList):
    await stop__(ctx, lvc)
    await asyncio.sleep(STOP_REFRESH)
    try:
        yield
    finally:
        q.is_stopped = False


async def set_pause__(
    ctx_g: tj.abc.Context | hk.Snowflakeish,
    lvc: lv.Lavalink,
    *,
    pause: t.Optional[bool],
    respond: bool = False,
    strict: bool = False,
) -> None:
    _ctx = None
    if isinstance(ctx_g, tj.abc.Context):
        _ctx = ctx_g
        assert ctx_g.guild_id is not None
        ctx_g = ctx_g.guild_id

    assert ctx_g is not None
    try:
        async with access_queue(ctx_g, lvc) as q:
            if q.is_stopped:
                if strict:
                    raise TrackStopped
                return
            if pause is None:
                pause = not q.is_paused
            if respond:
                assert _ctx is not None
                if pause and q.is_paused:
                    await err_reply(_ctx, content="❗ Already paused")
                    return
                if not (pause or q.is_paused):
                    await err_reply(_ctx, content="❗ Already resumed")
                    return

            np_pos = q.np_position
            if np_pos is None:
                raise NotPlaying

            q._last_np_position = np_pos if pause else curr_time_ms() - np_pos
            q.is_paused = pause
            if pause:
                await lvc.pause(ctx_g)
                msg = "▶️ Paused"
            else:
                await lvc.resume(ctx_g)
                msg = "⏸️ Resumed"
        if respond:
            assert _ctx is not None
            await reply(_ctx, content=msg)
    except (QueueIsEmpty, NotPlaying):
        if strict:
            raise
        pass


async def skip__(
    ctx_g: tj.abc.Context | hk.Snowflakeish,
    lvc: lv.Lavalink,
    *,
    advance: bool = True,
    change_repeat: bool = False,
) -> t.Optional[lv.TrackQueue]:
    _ctx = None
    if isinstance(ctx_g, tj.abc.Context):
        _ctx = ctx_g
        assert ctx_g.guild_id is not None
        ctx_g = ctx_g.guild_id

    async with access_queue(ctx_g, lvc) as q:
        skip = q.current
        if change_repeat and (
            q.repeat_mode is RepeatMode.ONE or q.repeat_mode is RepeatMode.ALL
        ):
            q.repeat_mode = RepeatMode.NONE if len(q) == 1 else RepeatMode.ALL
        if q.is_stopped and (next_t := q.next):
            if advance:
                q.adv()
                # q.is_stopped = False
            await lvc.play(ctx_g, next_t.track).start()
            if _ctx:
                await set_pause__(_ctx, lvc, pause=False)
            return skip
        try:
            return skip
        finally:
            await lvc.stop(ctx_g)


async def seek__(ctx: tj.abc.Context, lvc: lv.Lavalink, total_ms: int):
    assert ctx.guild_id is not None
    if total_ms < 0:
        raise IllegalArgument(Argument(total_ms, 0))
    async with access_queue(ctx, lvc) as q:
        assert q.current is not None
        if total_ms >= (song_len := q.current.track.info.length):
            raise IllegalArgument(Argument(total_ms, song_len))
        q._last_track_played = curr_time_ms() - total_ms
        await lvc.seek_millis(ctx.guild_id, total_ms)
        return total_ms


## Queue


@trigger_thinking()
async def play__(
    ctx: tj.abc.Context, lvc: lv.Lavalink, *, tracks: lv.Tracks, respond: bool = False
) -> None:
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if tracks.load_type == 'PLAYLIST_LOADED':
            await enqueue_tracks__(ctx, lvc, tracks=tracks, queue=q, respond=respond)
        else:
            await enqueue_track__(
                ctx, lvc, track=tracks.tracks[0], queue=q, respond=respond
            )


async def enqueue_track__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    *,
    track: lv.Track,
    queue: QueueList,
    respond: bool = False,
    ignore_stop: bool = False,
) -> None:
    assert ctx.guild_id is not None
    player = lvc.play(ctx.guild_id, track).requester(ctx.author.id).replace(False)
    queue.ext(player.to_track_queue())
    if respond:
        await def_reply(ctx, content=f"**`＋`** Added `{track.info.title}` to the queue")
    if not queue.is_stopped or ignore_stop:
        await player.start()


async def enqueue_tracks__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    *,
    tracks: lv.Tracks,
    queue: QueueList,
    respond: bool = False,
) -> None:
    assert ctx.guild_id is not None
    players = tuple(
        lvc.play(ctx.guild_id, t).requester(ctx.author.id).replace(False)
        for t in tracks.tracks
    )
    queue.ext(*map(lambda p: p.to_track_queue(), players))
    if respond:
        await def_reply(
            ctx,
            content=f"**`≡+`** Added `{len(tracks.tracks)} songs` from playlist `{tracks.playlist_info.name}` to the queue",
        )
    player = players[0]
    if not queue.is_stopped:
        await player.start()


## Info

...
