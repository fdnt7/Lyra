from .utils import *
from .checks import check, Checks
from .lavaimpl import (
    get_queue,
    get_data,
    set_data,
    access_queue,
    access_data,
    access_equalizer,
    edit_now_playing_components,
    QueueList,
    RepeatMode,
    NodeData,
)


STOP_REFRESH = 0.15

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


_P = t.ParamSpec('_P')


def attempt_to_connect(func: t.Callable[_P, VoidCoroutine]):
    async def inner(*args: _P.args, **kwargs: _P.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)
        lvc = next((a for a in kwargs.values() if isinstance(a, lv.Lavalink)), None)

        assert ctx and lvc
        p = get_pref(ctx)

        assert ctx.guild_id is not None
        conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)

        async def __join():
            if not conn:
                # Join the users voice channel if we are not already connected
                try:
                    await join__(ctx, None, lvc)
                except NotInVoice:
                    await err_reply(
                        ctx,
                        content=f"❌ Please join a voice channel first. You can also do `{p}join channel:` `[🔊 ...]`",
                    )
                    return
                except TimeoutError:
                    await err_reply(
                        ctx,
                        content="⌛ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
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

        await func(*args, **kwargs)

    return inner


async def init_listeners_voting(
    ctx: tj.abc.Context, bot: hk.GatewayBot, lvc: lv.Lavalink
):
    assert ctx.member and ctx.guild_id and ctx.client.cache

    cmd = ctx.command
    cmd_n = ''.join((get_pref(ctx), get_cmd_n(ctx)))

    row = (
        ctx.rest.build_action_row()
        .add_button(hk_msg.ButtonStyle.SUCCESS, 'vote')
        .set_emoji('🗳️')
        .add_to_container()
    )

    conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
    assert isinstance(conn, dict)

    channel: int = conn['channel_id']
    voice_states = ctx.client.cache.get_voice_states_view_for_channel(
        ctx.guild_id, channel
    )
    listeners = tuple(
        filter(
            lambda v: not v.member.is_bot,
            voice_states.values(),
        )
    )

    voted = {ctx.author.id}
    threshold = round((len(listeners) + 1) / 2)

    pad_f: t.Callable[[int], int] = lambda x: int(38 * x / 31 + 861 / 31)

    m = ctx.member

    def v_embed():
        assert ctx.member
        vote_n = len(voted)
        vote_b = ('─' * (pad_n := pad_f(len(ctx.member.display_name)))).replace(
            '─', '▬', pad_n * vote_n // threshold
        )
        return hk.Embed(
            title=f"🎫 Voting for command `{cmd_n}`",
            description=f"{m.mention} wanted to use the command `{cmd_n}`\n\n`{vote_b}` **{vote_n}/{threshold}**{' 🎉' if vote_n==threshold else ''}",
            color=0xC2CED5,
        )

    msg = await reply(
        ctx,
        ensure_result=True,
        embed=v_embed(),
        components=(row,),
    )

    np = (await get_queue(ctx, lvc)).current
    np_timeout = TIMEOUT if not np else np.track.info.length // 1_000

    with bot.stream(hk.InteractionCreateEvent, timeout=min(TIMEOUT, np_timeout)).filter(
        lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.message == msg
        and e.interaction.user.id in {u.user_id for u in listeners}
    ) as stream:

        async for event in stream:
            inter = event.interaction
            assert isinstance(inter, hk.ComponentInteraction)

            key = inter.custom_id
            if key == 'vote':
                if (user_id := inter.user.id) in voted:
                    await err_reply(inter, content="❗ You've already voted")
                    continue

                voted.add(user_id)

                await inter.create_initial_response(
                    hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
                )
                await inter.edit_initial_response(embed=v_embed())

            if len(voted) >= threshold:
                await reply(inter, content='☑️ Vote threshold reached')
                await inter.edit_initial_response(
                    components=(*disable_components(inter.app.rest, row),)
                )
                return

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, row),)
        )
        raise VotingTimeout


async def generate_nowplaying_embed__(
    guild_id: hk.Snowflakeish, cache: hk.api.Cache, lvc: lv.Lavalink, /
):
    q = await get_queue(guild_id, lvc)
    # e = '⏹️' if q.is_stopped else ('▶️' if q.is_paused else '⏸️')

    curr_t = q.current
    assert curr_t
    assert q.np_position

    t_info = curr_t.track.info
    req = cache.get_member(guild_id, curr_t.requester)
    assert req, "That member has left the guild"

    song_len = ms_stamp(t_info.length)
    # np_pos = q.np_position // 1_000
    # now = int(time.time())

    embed = (
        hk.Embed(
            title=f"🎧 {t_info.title}",
            description=f'📀 **{t_info.author}** ({song_len})',
            url=t_info.uri,
            color=0xF1656F,
            timestamp=dt.datetime.now().astimezone(),
        )
        .set_author(name="Currently playing")
        .set_footer(
            f"Requested by: {req.display_name}",
            icon=req.avatar_url or req.default_avatar_url,
        )
        .set_thumbnail(
            f"https://i.ytimg.com/vi/{t_info.identifier}/maxresdefault.jpg"
            # f"https://img.youtube.com/vi/{t_info.identifier}/maxresdefault.jpg"
        )
    )
    return embed


music_h = tj.AnyHooks()


@music_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    if t := isinstance(error, lv.NetworkError):
        await ctx.respond("⁉️ A network error has occurred")
        return t
    return t


@music_h.with_post_execution
async def post_execution(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
    cfg: GuildConfig = tj.inject(type=GuildConfig),
) -> None:
    assert ctx.guild_id

    from src.lib.music import access_data

    try:
        async with access_data(ctx, lvc) as d:
            d.out_channel_id = ctx.channel_id
    except NotConnected:
        pass


## Connections


loggerA = logging.getLogger(__name__ + '.connections')


async def join__(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel],
    lvc: lv.Lavalink,
    /,
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

    old_conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
    assert isinstance(old_conn, dict) or old_conn is None
    assert target_channel is not None

    # Check if the bot is already connected and the user tries to change
    if old_conn:

        old_channel: t.Optional[int] = old_conn['channel_id']
        # If it's the same channel
        assert old_channel
        if old_channel == target_channel:
            raise AlreadyConnected(old_channel)

        from .checks import check_others_not_in_vc__

        await check_others_not_in_vc__(ctx, hkperms.MOVE_MEMBERS, old_conn)
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

    async with access_data(ctx, lvc) as d:
        d.out_channel_id = ctx.channel_id

    loggerA.debug(f"In guild {ctx.guild_id} joined channel {target_channel}")
    return target_channel


async def leave__(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> hk.Snowflakeish:
    assert ctx.guild_id is not None

    if not (conn := lvc.get_guild_gateway_connection_info(ctx.guild_id)):
        raise NotConnected

    assert isinstance(conn, dict)
    curr_channel = conn['channel_id']
    assert isinstance(curr_channel, int)

    from .checks import check_others_not_in_vc__, DJ_PERMS

    await check_others_not_in_vc__(ctx, DJ_PERMS, conn)

    await cleanups__(ctx.guild_id, ctx.client.shards, lvc)

    loggerA.debug(f"In guild {ctx.guild_id} left   channel {curr_channel}")
    return curr_channel


async def cleanups__(
    guild: hk.Snowflakeish,
    shards: t.Optional[hk.ShardAware],
    lvc: lv.Lavalink,
    /,
    *,
    also_disconns: bool = True,
) -> None:
    await lvc.destroy(guild)
    if shards:
        if also_disconns:
            await shards.update_voice_state(guild, None)
        await lvc.wait_for_connection_info_remove(guild)
    await lvc.remove_guild_node(guild)
    await lvc.remove_guild_from_loops(guild)


## Playback


loggerB = logging.getLogger(__name__ + '.playback')


async def stop__(g_inf: GuildInferable, lvc: lv.Lavalink, /) -> None:
    g = snowflakeify(g_inf)
    async with access_queue(g, lvc) as q:
        q.is_stopped = True

    await lvc.stop(g)


async def stop_in_ctx__(
    g_inf: GuildInferable, lvc: lv.Lavalink, data: NodeData, /
) -> None:
    g = snowflakeify(g_inf)

    data.queue.is_stopped = True
    await set_data(g, lvc, data)
    await lvc.stop(g)


async def continue__(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> None:
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        q.is_stopped = False


async def wait_for_track_finish_event_fire(
    g_inf: GuildInferable, lvc: lv.Lavalink, data: NodeData, /
):
    while not (await get_data(snowflakeify(g_inf), lvc))._track_finished_fired:
        await asyncio.sleep(0.333)
    await asyncio.sleep(STOP_REFRESH)
    data._track_finished_fired = False


@ctxlib.asynccontextmanager
async def while_stop(g_inf: GuildInferable, lvc: lv.Lavalink, data: NodeData, /):
    await stop_in_ctx__(g_inf, lvc, data)
    try:
        yield
    finally:
        await wait_for_track_finish_event_fire(g_inf, lvc, data)
        data.queue.is_stopped = False


async def set_pause__(
    g_inf: GuildInferable,
    lvc: lv.Lavalink,
    /,
    *,
    pause: t.Optional[bool],
    respond: bool = False,
    strict: bool = False,
) -> None:
    _ctx = g_inf if isinstance(g_inf, Contextish) else None
    g = snowflakeify(g_inf)

    try:
        d = await get_data(g, lvc)
        q = d.queue
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

        q.is_paused = pause
        if pause:
            q._paused_np_position = np_pos
            await lvc.pause(g)
            e = '▶️'
            msg = "Paused"
        else:
            q._curr_t_started = curr_time_ms() - np_pos
            await lvc.resume(g)
            e = '⏸️'
            msg = "Resumed"

        await set_data(g, lvc, d)
        if respond:
            assert _ctx
            await reply(_ctx, content=f"{e} {msg}")

        if d._nowplaying_msg:
            if isinstance(_ctx, hk.ComponentInteraction):
                rest = _ctx.app.rest
            else:
                assert isinstance(_ctx, tj.abc.Context)
                rest = _ctx.rest

            assert d._nowplaying_components
            components = edit_components(
                rest,
                *d._nowplaying_components,
                edits=lambda x: x.set_emoji(e),
                predicates=lambda x: x.emoji in {'▶️', '⏸️'},
            )

            await edit_now_playing_components(rest, d, components)
    except (QueueEmpty, NotPlaying):
        if strict:
            raise
        pass


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
)
async def play_pause_impl(ctx: Contextish, /, *, lvc: lv.Lavalink):
    await set_pause__(ctx, lvc, pause=None, respond=True)


async def skip__(
    g_inf: GuildInferable,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    change_repeat: bool = False,
    change_stop: bool = True,
) -> t.Optional[lv.TrackQueue]:
    guild = snowflakeify(g_inf)

    async with access_queue(guild, lvc) as q:
        skip = q.current
        if change_repeat:
            q.reset_repeat()
        await lvc.stop(guild)
        if q.is_stopped and (next_t := q.next):
            if advance:
                q.adv()
            if change_stop:
                q.is_stopped = False
            await lvc.play(guild, next_t.track).start()
            await set_pause__(g_inf, lvc, pause=False)
        return skip


async def skip_impl(
    ctx_: Contextish, /, *, lvc: lv.Lavalink, bot: t.Optional[hk.GatewayBot] = None
):
    skip = await skip__(ctx_, lvc, change_repeat=True)

    assert skip is not None
    await reply(ctx_, content=f"⏭️ ~~`{skip.track.info.title}`~~")


async def back__(
    g_inf: GuildInferable,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    change_repeat: bool = False,
) -> lv.TrackQueue:
    g_inf = snowflakeify(g_inf)

    async with access_data(g_inf, lvc) as d:
        q = d.queue
        i = q.pos
        if change_repeat:
            q.reset_repeat()

        async with while_stop(g_inf, lvc, d):
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

        await lvc.play(g_inf, prev.track).start()
    await set_pause__(g_inf, lvc, pause=False)
    return prev


async def previous_impl(
    ctx_: Contextish, /, *, lvc: lv.Lavalink, bot: t.Optional[hk.GatewayBot] = None
):
    if (
        q := await get_queue(ctx_, lvc)
    ).repeat_mode is RepeatMode.NONE and not q.history:
        await err_reply(ctx_, content="❗ This is the start of the queue")
        return

    prev = await back__(ctx_, lvc)
    await reply(ctx_, content=f"⏮️ **`{prev.track.info.title}`**")


async def seek__(ctx: tj.abc.Context, lvc: lv.Lavalink, total_ms: int, /):
    assert ctx.guild_id is not None
    if total_ms < 0:
        raise IllegalArgument(Argument(total_ms, 0))
    async with access_queue(ctx, lvc) as q:
        assert q.current is not None
        if total_ms >= (song_len := q.current.track.info.length):
            raise IllegalArgument(Argument(total_ms, song_len))
        q._curr_t_started = curr_time_ms() - total_ms
        await lvc.seek_millis(ctx.guild_id, total_ms)
        return total_ms


## Queue


loggerC = logging.getLogger(__name__ + '.queue')


VALID_SOURCES = {
    "Youtube": 'yt',
    "Youtube Music": 'ytm',
    "Soundcloud": 'sc',
}


async def play__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    tracks: lv.Tracks,
    respond: bool = False,
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
    /,
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
        await reply(ctx, content=f"**`＋`** Added `{track.info.title}` to the queue")
    if not queue.is_stopped or ignore_stop:
        await player.start()


async def enqueue_tracks__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
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
        await reply(
            ctx,
            content=f"**`≡+`** Added `{len(tracks.tracks)} songs` from playlist `{tracks.playlist_info.name}` to the queue",
        )
    player = next(iter(players))
    if not queue.is_stopped:
        await player.start()


async def remove_track__(
    ctx: tj.abc.Context, track: t.Optional[str], lvc: lv.Lavalink, /
) -> lv.TrackQueue:
    assert ctx.guild_id is not None

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
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
            q, key=lambda t: SequenceMatcher(None, t.track.info.title, track).ratio()
        )
        i = q.index(rm)

    try:
        from .checks import check_others_not_in_vc

        await check_others_not_in_vc(ctx, lvc)
    except OthersInVoice:
        if rm.requester != ctx.author.id:
            raise PlaybackChangeRefused

        # q.is_stopped = False

    if rm == np:
        async with while_stop(ctx, lvc, d):
            await skip__(ctx, lvc, advance=False, change_repeat=True)

    if i < q.pos:
        q.pos = max(0, q.pos - 1)
    q.sub(rm)

    loggerC.info(
        f"In guild {ctx.guild_id} track [{i: >3}+1/{len(q)}] removed: '{rm.track.info.title}'"
    )

    await set_data(ctx.guild_id, lvc, d)
    return rm


async def remove_tracks__(
    ctx: tj.abc.Context, start: int, end: int, lvc: lv.Lavalink, /
) -> list[lv.TrackQueue]:
    assert ctx.guild_id is not None

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    if not (1 <= start <= end <= len(q)):
        raise IllegalArgument(Argument((start, end), (1, len(q))))

    i_s = start - 1
    i_e = end - 1
    t_n = end - i_s
    rm = q[i_s:end]
    if q.current in rm:
        q.reset_repeat()
        async with while_stop(ctx, lvc, d):
            if next_t := None if len(q) <= end else q[end]:
                await set_pause__(ctx, lvc, pause=False)
                await lvc.play(ctx.guild_id, next_t.track).start()
    if i_s < q.pos:
        q.pos = max(0, i_s + (q.pos - i_e - 1))
    q.sub(*rm)

    loggerC.info(
        f"""In guild {ctx.guild_id} tracks [{i_s: >3}~{i_e: >3}/{len(q)}] removed: '{', '.join(("'%s'" %  t.track.info.title) for t in rm)}'"""
    )

    await set_data(ctx.guild_id, lvc, d)
    return rm


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def shuffle_impl(ctx_: Contextish, /, *, lvc: lv.Lavalink):
    async with access_queue(ctx_, lvc) as q:
        if not q.upcoming:
            await err_reply(ctx_, content=f"❗ This is the end of the queue")
            return
        q.shuffle()

        await reply(
            ctx_,
            content=f"🔀 Shuffled the upcoming tracks. `(Track #{q.pos+2}-{len(q)}; {len(q) - q.pos - 1} tracks)`",
        )


async def insert_track__(
    ctx: tj.abc.Context, insert: int, track: t.Optional[int], lvc: lv.Lavalink, /
) -> lv.TrackQueue:
    assert ctx.guild_id is not None

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    np = q.current
    p_ = q.pos
    if track is None:
        if not np:
            raise InvalidArgument(Argument(np, track))
        t_ = p_
        ins = np
    else:
        t_ = track - 1
        ins = q[t_]

    i_ = insert - 1
    if t_ in {i_, insert}:
        raise ValueError
    if not ((0 <= t_ < len(q)) and (0 <= i_ < len(q))):
        raise IllegalArgument(Argument((track, insert), (1, len(q))))

    if t_ < p_ <= i_:
        q.decr()
    elif i_ < p_ < t_:
        q.adv()

    elif i_ < p_ == t_:
        await back__(ctx, lvc, advance=False, change_repeat=True)

    elif p_ == t_ < i_:
        async with while_stop(ctx, lvc, d):
            await skip__(ctx, lvc, advance=False, change_repeat=True, change_stop=False)

    q[t_] = REMOVED
    q.insert(insert, ins)
    q.remove(REMOVED)

    await set_data(ctx.guild_id, lvc, d)
    return ins


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def repeat_impl(
    ctx_: Contextish, mode: t.Optional[str], /, *, lvc: lv.Lavalink
) -> None:
    """Select a repeat mode for the queue"""
    async with access_data(ctx_, lvc) as d:
        q = d.queue
        if mode is None:
            modes = tuple(m.value for m in RepeatMode)
            mode = modes[(modes.index(q.repeat_mode.value) + 1) % 3]
            assert mode is not None
        m = q.set_repeat(mode)

    match m:
        case RepeatMode.NONE:
            e = '➡️'
            msg = "Disabled repeat"
        case RepeatMode.ALL:
            e = '🔁'
            msg = "Repeating the entire queue"
        case RepeatMode.ONE:
            e = '🔂'
            msg = "Repeating only this current track"
        case _:
            raise NotImplementedError

    await reply(ctx_, content=f"{e} {msg}")
    if d._nowplaying_msg:
        if isinstance(ctx_, hk.ComponentInteraction):
            rest = ctx_.app.rest
        else:
            assert isinstance(ctx_, tj.abc.Context)
            rest = ctx_.rest

        assert d._nowplaying_components
        components = edit_components(
            rest,
            *d._nowplaying_components,
            edits=lambda x: x.set_emoji(e),
            predicates=lambda x: x.emoji in {'➡️', '🔁', '🔂'},
        )

        await edit_now_playing_components(rest, d, components)


## Info


async def generate_queue_embeds__(
    ctx: tj.abc.Context, lvc: lv.Lavalink, /
) -> tuple[hk.Embed]:
    assert not ((ctx.guild_id is None) or (ctx.cache is None))
    q = await get_queue(ctx, lvc)
    if np := q.current:
        np_info = np.track.info
        req = ctx.cache.get_member(ctx.guild_id, np.requester)
        assert req is not None
        np_text = f"```arm\n{q.pos+1: >2}. {ms_stamp(np_info.length):>6} | {wr(np_info.title, 50)} |\n````Requested by:` {req.mention}"
    else:
        np_text = f"```yaml\n{'---':^63}\n```"

    queue_durr = sum(t.track.info.length for t in q)
    queue_elapsed = sum(t.track.info.length for t in q.history) + (q.np_position or 0)
    queue_eta = queue_durr - queue_elapsed

    q = await get_queue(ctx, lvc)
    prev = None if not (his := q.history) else his[-1]
    upcoming = q.upcoming

    desc = (
        ""
        if q.repeat_mode is RepeatMode.NONE
        else (
            "**```diff\n+| Repeating this entire queue\n```**"
            if q.repeat_mode is RepeatMode.ALL
            else "**```diff\n-| Repeating the current track\n```**"
        )
    )

    _base_embed = hk.Embed(
        title="💿 Queue",
        description=desc,
        color=(32, 126, 172),
    ).set_footer(f"Queue Duration: {ms_stamp(queue_elapsed)} / {ms_stamp(queue_durr)}")

    _format = f"```{'brainfuck' if q.repeat_mode is RepeatMode.ONE else 'css'}\n%s\n```"
    _format_prev = (
        f"```{'brainfuck' if q.repeat_mode is RepeatMode.ONE else 'yaml'}\n%s\n```"
    )
    _empty = f"{'---':^63}"

    import copy

    np_embed = (
        copy.deepcopy(_base_embed)
        .add_field(
            "Previous",
            _format_prev
            % (
                f"{q.pos: >2}․ {ms_stamp(prev.track.info.length):>6} # {wr(prev.track.info.title, 51)}"
                if prev
                else _empty
            ),
        )
        .add_field(
            f"{'🎶 ' if np and not q.is_paused else ''}Now playing",
            np_text,
        )
        .add_field(
            "Next up",
            _format
            % (
                "\n".join(
                    f"{j: >2}․ {ms_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 51)}"
                    for j, t_ in enumerate(upcoming[:Q_DIV], q.pos + 2)
                )
                or _empty,
            ),
        )
    )

    prev_embeds = [
        copy.deepcopy(_base_embed).add_field(
            "Previous",
            _format_prev
            % "\n".join(
                f"{j: >2}․ {ms_stamp(t_.track.info.length):>6} # {wr(t_.track.info.title, 51)}"
                for j, t_ in enumerate(
                    prev_slice,
                    1 + max(0, i) * Q_DIV + (0 if i == -1 else len(his[:-1]) % Q_DIV),
                )
            ),
        )
        for i, prev_slice in enumerate(chunk_b(his[:-1], Q_DIV), -1)
        if prev_slice
    ]

    next_embeds = [
        copy.deepcopy(_base_embed).add_field(
            "Next up",
            _format
            % "\n".join(
                f"{j: >2}․ {ms_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 51)}"
                for j, t_ in enumerate(next_slice, q.pos + 2 + i * Q_DIV)
            ),
        )
        for i, next_slice in enumerate(chunk(upcoming[Q_DIV:], Q_DIV), 1)
        if next_slice
    ]

    return tuple(prev_embeds + [np_embed] + next_embeds)


## Tuning


loggerE = logging.getLogger(__name__ + ".tuning")


async def set_mute__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
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
