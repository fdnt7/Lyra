from .utils import *

STOP_REFRESH = 0.15
DJ_PERMS = P.DEAFEN_MEMBERS | P.MUTE_MEMBERS

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

REPEAT_MODES_ALL = 'off|0|one|o|1|all|a|q'.split('|')


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


@a.define
class QueueList(list):
    pos: int = 0
    repeat_mode: RepeatMode = RepeatMode.NONE
    is_paused: bool = a.field(factory=bool, kw_only=True)
    is_stopped: bool = a.field(factory=bool, kw_only=True)
    _last_np_position: t.Optional[int] = a.field(default=None, init=False)
    _last_track_played: int = a.field(factory=curr_time_ms, init=False)

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

    @classmethod
    def from_list(cls, l: list[lv.TrackQueue]):
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
        self.reset_repeat()
        self.pos = 0

    def reset_repeat(self) -> None:
        if self.repeat_mode is RepeatMode.ONE or self.repeat_mode is RepeatMode.ALL:
            self.repeat_mode = RepeatMode.NONE if len(self) == 1 else RepeatMode.ALL


@a.define
class Equalizer(object):
    _volume: int = a.field(default=100, init=False)
    is_muted: bool = a.field(factory=bool, kw_only=True)

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, y: int):
        self._volume = min(max(y, 0), 100)

    def up(self, amount: int = 10):
        self.volume += amount

    def down(self, amount: int = 10):
        self.volume -= amount

    def mute(self):
        ...


@a.define
class NodeData:
    queue: QueueList = a.field(factory=QueueList, kw_only=True)
    equalizer: Equalizer = a.field(factory=Equalizer, kw_only=True)
    out_channel_id: t.Optional[hk.Snowflakeish] = a.field(default=None, kw_only=True)
    ...


loggerX = logging.getLogger(__name__ + '.events')


class EventHandler:
    async def track_start(self, lvc: lv.Lavalink, event: lv.TrackStart) -> None:
        t = (await lvc.decode_track(event.track)).title
        async with access_queue(event.guild_id, lvc) as q:
            l = len(q)
            q._last_track_played = curr_time_ms()
            loggerX.debug(
                f"In guild {event.guild_id} track [{q.pos: >3}+1/{l}] started: '{t}'"
            )

            # await asyncio.sleep(1)
            # await skip__(event.guild_id, lvc)

    async def track_finish(self, lvc: lv.Lavalink, event: lv.TrackFinish) -> None:
        t = (await lvc.decode_track(event.track)).title
        async with access_queue(event.guild_id, lvc) as q:
            l = len(q)
            if q.is_stopped:
                loggerX.info(
                    f"In guild {event.guild_id} track [{q.pos: >3}+1/{l}] stopped: '{t}'"
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
                loggerX.debug(
                    f"In guild {event.guild_id} track [{q.pos: >3}+1/{l}] ended  : '{t}'"
                )

    async def track_exception(self, lvc: lv.Lavalink, event: lv.TrackException) -> None:
        t = (await lvc.decode_track(event.track)).title
        q = await get_queue(event.guild_id, lvc)
        l = len(q)

        msg = f"In guild {event.guild_id} track [{q.pos: >3}+1/{l}] {{0}}: '{t}'\n\t{event.exception_message}\n\tCaused by: {event.exception_cause}"

        match event.exception_severity:
            case 'COMMON':
                loggerX.error(msg.format('blocked'))
            case 'SUSPICIOUS':
                loggerX.warning(msg.format('malformed'))
            case _:
                raise NotImplementedError

        # If a track was unable to be played, skip it
        await skip__(
            event.guild_id,
            lvc,
            advance=not q.is_stopped,
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


A = t.ParamSpec('A')


def check(checks: Checks, perms: P = P.NONE):
    def decorator(func: t.Callable[..., t.Coroutine]):
        async def wrapper(ctx: tj.abc.Context, *args: t.Any, lvc: lv.Lavalink):
            assert ctx.member is not None

            try:
                if perms:
                    auth_perms = await tj.utilities.fetch_permissions(
                        ctx.client, ctx.member, channel=ctx.channel_id
                    )
                    if not (auth_perms & (perms | P.ADMINISTRATOR)):
                        raise Forbidden(perms)

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

        async def __join():
            if not conn:
                # Join the users voice channel if we are not already connected
                try:
                    await join__(ctx, None, lvc)
                except NotInVoice:
                    await err_reply(
                        ctx,
                        content=f"❌ Please join a voice channel first. You can also do `/join channel:` `[🔊 ...]`",
                    )
                    return
                except TimeoutError:
                    await def_reply(
                        ctx,
                        content="⏳ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
                    )
                    return
            return True

        ch = ctx.get_channel()
        assert ch is not None
        if isinstance(ctx, tj.abc.MessageContext):
            async with ch.trigger_typing():
                if not await __join():
                    return
        else:
            if not await __join():
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
async def access_queue(ctx_g: Contextish, lvc: lv.Lavalink):
    ctx_g = snowflakeify(ctx_g)

    data = await get_data(ctx_g, lvc)
    try:
        yield data.queue
    finally:
        await set_data(ctx_g, lvc, data)


@asynccontextmanager
async def access_equalizer(ctx_g: Contextish, lvc: lv.Lavalink):
    ctx_g = snowflakeify(ctx_g)

    data = await get_data(ctx_g, lvc)
    try:
        yield data.equalizer
    finally:
        await set_data(ctx_g, lvc, data)


@asynccontextmanager
async def access_node_data(ctx_g: Contextish, lvc: lv.Lavalink):
    ctx_g = snowflakeify(ctx_g)

    data = await get_data(ctx_g, lvc)
    try:
        yield data
    finally:
        await set_data(ctx_g, lvc, data)


async def get_queue(ctx_g: Contextish, lvc: lv.Lavalink) -> QueueList:
    ctx_g = snowflakeify(ctx_g)

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


loggerA = logging.getLogger(__name__ + '.connections')


async def join__(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel],
    lvc: lv.Lavalink,
) -> hk.Snowflake:
    """Joins your voice channel."""
    assert ctx.guild_id is not None

    if not (ctx.client.cache and ctx.client.shards):
        raise InternalError

    if channel is None:
        # If user is connected to a voice channel
        if (
            voice_state := ctx.client.cache.get_voice_state(ctx.guild_id, ctx.author)
        ) is not None:
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
        raise
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

    async with access_node_data(ctx, lvc) as d:
        d.out_channel_id = ctx.channel_id

    loggerA.debug(f"In guild {ctx.guild_id} joined channel {target_channel}")
    return target_channel


async def leave__(ctx: tj.abc.Context, lvc: lv.Lavalink) -> hk.Snowflakeish:
    assert ctx.guild_id is not None

    if not (conn := await lvc.get_guild_gateway_connection_info(ctx.guild_id)):
        raise NotConnected

    assert isinstance(conn, dict)
    curr_channel = conn['channel_id']
    assert isinstance(curr_channel, int)

    await check_others_not_in_vc__(ctx, DJ_PERMS, conn)

    async with access_queue(ctx, lvc) as q:
        q.clr()

    await lvc.destroy(ctx.guild_id)
    if ctx.client.shards:
        # Set voice channel to None
        await ctx.client.shards.update_voice_state(ctx.guild_id, None)
        await lvc.wait_for_connection_info_remove(ctx.guild_id)

    # We must manually remove the node and queue loop from lavasnek
    await lvc.remove_guild_node(ctx.guild_id)
    await lvc.remove_guild_from_loops(ctx.guild_id)

    loggerA.debug(f"In guild {ctx.guild_id} left   channel {curr_channel}")
    return curr_channel


## Playback


loggerB = logging.getLogger(__name__ + '.playback')


async def stop__(ctx_g: Contextish, lvc: lv.Lavalink) -> None:
    ctx_g = snowflakeify(ctx_g)
    async with access_queue(ctx_g, lvc) as q:
        q.is_stopped = True

    await lvc.stop(ctx_g)  # Stop the player


async def continue__(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        q.is_stopped = False


@asynccontextmanager
async def while_stop(ctx_g: Contextish, lvc: lv.Lavalink, q: QueueList):
    await stop__(ctx_g, lvc)
    await asyncio.sleep(STOP_REFRESH)
    try:
        yield
    finally:
        q.is_stopped = False


async def set_pause__(
    ctx_g: Contextish,
    lvc: lv.Lavalink,
    *,
    pause: t.Optional[bool],
    respond: bool = False,
    strict: bool = False,
) -> None:
    _ctx = ctx_g if isinstance(ctx_g, tj.abc.Context) else None
    ctx_g = snowflakeify(ctx_g)

    try:
        async with access_queue(ctx_g, lvc) as q:
            if q.is_stopped:
                if strict:
                    raise TrackStopped
                return
            if pause is None:
                pause = not q.is_paused
            if respond and _ctx:
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
    ctx_g: Contextish,
    lvc: lv.Lavalink,
    *,
    advance: bool = True,
    change_repeat: bool = False,
    change_stop: bool = True,
) -> t.Optional[lv.TrackQueue]:
    guild = snowflakeify(ctx_g)

    async with access_queue(guild, lvc) as q:
        skip = q.current
        if change_repeat:
            q.reset_repeat()
        if q.is_stopped and (next_t := q.next):
            if advance:
                q.adv()
            if change_stop:
                q.is_stopped = False
            await lvc.play(guild, next_t.track).start()
            await set_pause__(ctx_g, lvc, pause=False)
            return skip
        try:
            return skip
        finally:
            await lvc.stop(guild)


async def back__(
    ctx_g: Contextish,
    lvc: lv.Lavalink,
    *,
    advance: bool = True,
    change_repeat: bool = False,
) -> lv.TrackQueue:
    ctx_g = snowflakeify(ctx_g)

    async with access_queue(ctx_g, lvc) as q:
        i = q.pos
        if change_repeat:
            q.reset_repeat()
        async with while_stop(ctx_g, lvc, q):
            match q.repeat_mode:
                case RepeatMode.ALL:
                    i -= 1
                    i %= len(q)
                    prev = q[i]
                case RepeatMode.ONE:
                    prev = q.current
                    assert prev is not None
                case RepeatMode.NONE:
                    prev = q.history[-1]
                    i -= 1

        if advance:
            q.pos = i

        await lvc.play(ctx_g, prev.track).start()
        await set_pause__(ctx_g, lvc, pause=False)
        return prev


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


loggerC = logging.getLogger(__name__ + '.queue')


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
    player = next(iter(players))
    if not queue.is_stopped:
        await player.start()


async def remove_track__(
    ctx: tj.abc.Context, track: t.Optional[str], lvc: lv.Lavalink
) -> lv.TrackQueue:
    assert ctx.guild_id is not None

    q = await get_queue(ctx, lvc)
    np = q.current
    if track is None:
        if not np:
            raise InvalidArgument(Argument(track, None))
        rm = np
        i = q.pos
    elif track.isdigit():
        t = int(track)
        if not (1 <= t <= len(q)):
            raise IllegalArgument(Argument(t, (1, len(q))))
        i = t - 1
        rm = q[i]
    else:
        rm = max(
            *q,
            key=lambda t: SequenceMatcher(None, t.track.info.title, track).ratio(),
        )
        i = q.index(rm)

    try:
        await check_others_not_in_vc(ctx, lvc)
    except OthersInVoice:
        if rm.requester != ctx.author.id:
            raise PlaybackChangeRefused

        # q.is_stopped = False

    async with access_queue(ctx, lvc) as q:
        if rm == np:
            async with while_stop(ctx, lvc, q):
                await skip__(ctx, lvc, advance=False, change_repeat=True)

        if i < q.pos:
            q.pos = max(0, q.pos - 1)
        q.sub(rm)

        loggerC.info(
            f"In guild {ctx.guild_id} track [{i: >3}+1/{len(q)}] removed: '{rm.track.info.title}'"
        )
        return rm


async def remove_tracks__(
    ctx: tj.abc.Context, start: int, end: int, lvc: lv.Lavalink
) -> list[lv.TrackQueue]:
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if not (1 <= start <= end <= len(q)):
            raise IllegalArgument(Argument((start, end), (1, len(q))))

        i_s = start - 1
        i_e = end - 1
        t_n = end - i_s
        rm = q[i_s:end]
        if q.current in rm:
            q.reset_repeat()
            async with while_stop(ctx, lvc, q):
                pass
            if next_t := None if len(q) <= end else q[end]:
                await set_pause__(ctx, lvc, pause=False)
                await lvc.play(ctx.guild_id, next_t.track).start()
        if i_s < q.pos:
            q.pos = i_s + (q.pos - i_e - 1)
        q.sub(*rm)

        loggerC.info(
            f"""In guild {ctx.guild_id} tracks [{i_s: >3}~{i_e: >3}+1/{len(q)}] removed: '{', '.join(("'%s'" %  t.track.info.title) for t in rm)}'"""
        )
        return rm


async def insert_track__(
    ctx: tj.abc.Context,
    insert: int,
    track: t.Optional[int],
    lvc: lv.Lavalink,
) -> lv.TrackQueue:
    assert ctx.guild_id is not None

    q = await get_queue(ctx, lvc)
    np = q.current
    p_ = q.pos
    if track is None:
        if not np:
            raise InvalidArgument(Argument(np, track))
        t_ = q.pos
        ins = np
    else:
        t_ = track - 1
        ins = q[t_]

    i_ = insert - 1
    if t_ in (i_, insert):
        raise ValueError
    if not ((0 <= t_ < len(q)) and (0 <= i_ < len(q))):
        raise IllegalArgument(Argument((track, insert), (1, len(q))))

    async with access_queue(ctx, lvc):
        if t_ < p_ <= i_:
            q.decr()
        elif i_ < p_ < t_:
            q.adv()

        prev = i_ < p_ == t_
        if (skip := p_ == t_ < i_) or prev:
            async with while_stop(ctx, lvc, q):
                if skip:
                    await skip__(ctx, lvc, advance=False, change_repeat=True)
                elif prev:
                    await back__(ctx, lvc, advance=False, change_repeat=True)

        q[t_] = REMOVED
        q.insert(insert, ins)
        q.remove(REMOVED)

        return ins


## Info


...


## Tuning


loggerE = logging.getLogger(__name__ + ".tuning")


async def set_mute__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    *,
    mute: t.Optional[bool],
    respond: bool = False,
) -> None:
    assert not (ctx.cache is None or ctx.guild_id is None)
    me = ctx.cache.get_me()
    assert me is not None

    async with access_equalizer(ctx, lvc) as eq:
        if mute is None:
            mute = not eq.is_muted
        if mute and eq.is_muted:
            await err_reply(ctx, content="❗ Already muted")
            return
        if not (mute or eq.is_muted):
            await err_reply(ctx, content="❗ Already unmuted")
            return

        if mute:
            await ctx.rest.edit_member(ctx.guild_id, me, mute=True)
            msg = "🔇 Muted"
        else:
            await ctx.rest.edit_member(ctx.guild_id, me, mute=False)
            msg = "🔊 Unmuted"

        eq.is_muted = mute
        if respond:
            await reply(ctx, content=msg)
