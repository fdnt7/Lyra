import typing as t
import asyncio
import logging
import contextlib as ctxlib

import tanjun as tj
import alluka as al
import lavasnek_rs as lv


from src.lib.music import STOP_REFRESH, music_h
from src.lib.utils import (
    ButtonBuilderType,
    GuildOrRESTInferable,
    GuildOrInferable,
    RESTInferable,
    Contextish,
    EmojiRefs,
    guild_c,
    get_rest,
    get_client,
    say,
    err_say,
    infer_guild,
    edit_components,
)
from src.lib.checks import Checks, check
from src.lib.extras import to_stamp, to_ms
from src.lib.lavaimpl import (
    RepeatMode,
    NodeData,
    get_data,
    set_data,
    access_data,
    get_queue,
    access_queue,
)
from src.lib.errors import (
    TrackStopped,
    NotPlaying,
    QueueEmpty,
    IllegalArgument,
    Argument,
)
from src.lib.consts import LOG_PAD


playback = (
    tj.Component(name='Playback', strict=True).add_check(guild_c).set_hooks(music_h)
)


logger = logging.getLogger(f"{'playback':<{LOG_PAD}}")
logger.setLevel(logging.DEBUG)


async def stop(g_inf: GuildOrInferable, lvc: lv.Lavalink, /) -> None:
    async with access_queue(g_inf, lvc) as q:
        q.is_stopped = True

    await lvc.stop(infer_guild(g_inf))


async def stop_in_ctxmng(
    g_inf: GuildOrInferable, lvc: lv.Lavalink, data: NodeData, /
) -> None:
    g = infer_guild(g_inf)

    data.queue.is_stopped = True
    await set_data(g, lvc, data)
    await lvc.stop(g)


async def unstop(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> None:
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        q.is_stopped = False


async def wait_for_track_finish_event_fire(
    g_inf: GuildOrInferable, lvc: lv.Lavalink, data: NodeData, /
):
    while not (await get_data(infer_guild(g_inf), lvc)).track_stopped_fired:
        await asyncio.sleep(STOP_REFRESH)
    data.track_stopped_fired = False


@ctxlib.asynccontextmanager
async def while_stop(g_inf: GuildOrInferable, lvc: lv.Lavalink, data: NodeData, /):
    await stop_in_ctxmng(g_inf, lvc, data)
    prior_playing = data.queue.current
    try:
        yield
    finally:
        if prior_playing:
            await wait_for_track_finish_event_fire(g_inf, lvc, data)
        data.queue.is_stopped = False


async def set_pause(
    g_r_inf: GuildOrRESTInferable,
    lvc: lv.Lavalink,
    /,
    *,
    pause: t.Optional[bool],
    respond: bool = False,
    strict: bool = False,
    update_controller: bool = False,
) -> None:
    g = infer_guild(g_r_inf)

    try:
        client = get_client(g_r_inf)
        erf = client.get_type_dependency(EmojiRefs)
        assert erf

        d = await get_data(g, lvc)
        q = d.queue
        if q.is_stopped:
            if strict:
                raise TrackStopped
            return
        if pause is None:
            pause = not q.is_paused
        if respond:
            if pause and q.is_paused:
                await err_say(g_r_inf, content="❗ Already paused")
                return
            if not (pause or q.is_paused):
                await err_say(g_r_inf, content="❗ Already resumed")
                return

        np_pos = q.np_position
        if np_pos is None:
            raise NotPlaying

        q.is_paused = pause
        if pause:
            q.update_paused_np_position(np_pos)
            await lvc.pause(g)
            e = '▶️'
            msg = "Paused"
        else:
            q.update_curr_t_started(-np_pos)
            await lvc.resume(g)
            e = '⏸️'
            msg = "Resumed"

        await set_data(g, lvc, d)
        if respond:
            if isinstance(g_r_inf, Contextish):
                await say(g_r_inf, show_author=True, content=f"{e} {msg}")
            else:
                g_r_inf

        if update_controller and d.nowplaying_msg:
            if not isinstance(g_r_inf, RESTInferable):
                raise RuntimeError(
                    "`g_r_inf` was not type `RESTInferable` but `update_controller` was passed `True`"
                )
            rest = get_rest(g_r_inf)

            assert d.nowplaying_components
            edits: t.Callable[
                [ButtonBuilderType], ButtonBuilderType
            ] = lambda x: x.set_emoji(erf[f"{msg[:-1].casefold()}_b"])
            predicates: t.Callable[[ButtonBuilderType], bool] = lambda x: x.emoji in {
                erf["pause_b"],
                erf["resume_b"],
            }

            components = edit_components(
                rest,
                *d.nowplaying_components,
                edits=edits,
                predicates=predicates,
            )

            await d.edit_now_playing_components(rest, components)
    except (QueueEmpty, NotPlaying):
        if strict:
            raise
        pass


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
)
async def play_pause_impl(ctx: Contextish, lvc: lv.Lavalink):
    await set_pause(ctx, lvc, pause=None, respond=True, update_controller=True)


async def skip(
    g_inf: GuildOrInferable,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    change_repeat: bool = False,
    change_stop: bool = True,
) -> t.Optional[lv.TrackQueue]:
    async with access_queue(g_inf, lvc) as q:
        skip = q.current
        if change_repeat:
            q.reset_repeat()
        await lvc.stop(g := infer_guild(g_inf))
        if q.is_stopped:
            if advance:
                q.adv()
            if next_t := q.next:
                await lvc.play(g, next_t.track).start()
        if change_stop:
            q.is_stopped = False
        await set_pause(g_inf, lvc, pause=False)
        return skip


async def skip_abs(ctx_: Contextish, lvc: lv.Lavalink):
    skip_t = await skip(ctx_, lvc, change_repeat=True)

    assert skip_t is not None
    await say(ctx_, show_author=True, content=f"⏭️ ~~`{skip_t.track.info.title}`~~")


async def back(
    ctx_: Contextish,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    change_repeat: bool = False,
) -> lv.TrackQueue:
    async with access_data(ctx_, lvc) as d:
        q = d.queue
        i = q.pos
        if change_repeat:
            q.reset_repeat()

        async with while_stop(ctx_, lvc, d):
            rep = q.repeat_mode
            if rep is RepeatMode.ALL:
                i -= 1
                i %= len(q)
                prev = q[i]
            elif rep is RepeatMode.ONE:
                prev = q.current
                assert prev is not None
            else:
                prev = q.history[-1]
                i -= 1

            if advance:
                q.pos = i

        await lvc.play(infer_guild(ctx_), prev.track).start()
    await set_pause(ctx_, lvc, pause=False)
    return prev


async def previous_abs(ctx_: Contextish, lvc: lv.Lavalink):
    if (
        q := await get_queue(ctx_, lvc)
    ).repeat_mode is RepeatMode.NONE and not q.history:
        await err_say(ctx_, content="❗ This is the start of the queue")
        return

    prev = await back(ctx_, lvc)
    await say(ctx_, show_author=True, content=f"⏮️ **`{prev.track.info.title}`**")


async def seek(ctx: tj.abc.Context, lvc: lv.Lavalink, total_ms: int, /):
    assert ctx.guild_id
    if total_ms < 0:
        raise IllegalArgument(Argument(total_ms, 0))
    async with access_queue(ctx, lvc) as q:
        assert q.current is not None
        if total_ms >= (song_len := q.current.track.info.length):
            raise IllegalArgument(Argument(total_ms, song_len))
        q.update_curr_t_started(-total_ms)
        await lvc.seek_millis(ctx.guild_id, total_ms)
        return total_ms


# ~


# Play-Pause


@tj.as_slash_command(
    'play-pause', "Toggles the playback of the current song between play and pause"
)
#
@tj.as_message_command('playpause', 'play-pause', 'pp', '>||')
async def play_pause_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Pauses the current song."""
    await play_pause_impl(ctx, lvc)


# Pause


@tj.as_slash_command('pause', "Pauses the current song")
#
@tj.as_message_command('pause', '>', 'ps')
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
)
async def pause_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Pauses the current song."""
    assert ctx.guild_id

    await set_pause(ctx, lvc, pause=True, respond=True, update_controller=True)


# Resume


@tj.as_slash_command("resume", "Resumes the current track")
#
@tj.as_message_command('resume', 'res', 'rs', '||')
#
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
)
async def resume_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Resumes the current song."""
    assert not ((ctx.guild_id is None) or (ctx.member is None))

    await set_pause(ctx, lvc, pause=False, respond=True, update_controller=True)


# Stop


@tj.as_slash_command('stop', "Stops the current track; skip to play again")
#
@tj.as_message_command('stop', 'st', '[]')
#
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
)
async def stop_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Stops the currently playing song."""
    await stop(ctx, lvc)
    await say(ctx, content="⏹️ Stopped")


# Fast-forward


@tj.with_float_slash_option(
    'seconds', "Fast-foward by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command('fast-forward', "Fast-forwards the current track")
#
@tj.with_argument('seconds', converters=float, default=10.0)
@tj.with_parser
@tj.as_message_command(
    'fastforward', 'fast-forward', 'forward', 'fw', 'fwd', 'ff', '>>'
)
#
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
    | Checks.PAUSE
)
async def fastforward_(
    ctx: tj.abc.MessageContext,
    seconds: float,
    lvc: al.Injected[lv.Lavalink],
):
    async with access_queue(ctx, lvc) as q:
        assert not ((q.current is None) or (q.np_position is None))
        np_info = q.current.track.info
        old_np_ms = q.np_position
        new_np_ms = old_np_ms + int(seconds * 1000)

        try:
            await seek(ctx, lvc, new_np_ms)
        except IllegalArgument:
            await skip(ctx, lvc, change_stop=False)
            await say(
                ctx,
                content=f"❕⏭️ ~~`{np_info.title}`~~ *(The fast-forwarded time was too large; **Skipping** to the next track)*",
            )
        fmt_sec = f"{I if (I := int(seconds)) == seconds else f'{seconds:.3f}'}s"
        await say(
            ctx,
            content=f"⏩ ~~`{to_stamp(old_np_ms)}`~~ **❯❯** **`{to_stamp(new_np_ms)}`** `({fmt_sec})`",
        )


# Rewind


@tj.with_float_slash_option(
    'seconds', "Rewind by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command('rewind', "Rewinds the current track")
#
@tj.with_argument('seconds', converters=float, default=10.00)
@tj.with_parser
@tj.as_message_command('rewind', 'rw', 'rew', '<<')
#
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
    | Checks.PAUSE
)
async def rewind_(
    ctx: tj.abc.Context,
    seconds: float,
    lvc: al.Injected[lv.Lavalink],
):
    async with access_queue(ctx, lvc) as q:
        assert not ((q.current is None) or (q.np_position is None))
        old_np_ms = q.np_position
        new_np_ms = old_np_ms - int(seconds * 1000)

        try:
            await seek(ctx, lvc, new_np_ms)
        except IllegalArgument:
            await seek(ctx, lvc, 0)
            await say(
                ctx,
                content=f"❕◀️ *The rewinded time was too large; **Restarted** the current track*",
            )
        fmt_sec = f"{I if (I := int(seconds)) == seconds else f'{seconds:.3f}'}s"
        await say(
            ctx,
            content=f"⏪ **`{to_stamp(new_np_ms)}`** **❮❮** ~~`{to_stamp(old_np_ms)}`~~ `({fmt_sec})`",
        )


# Skip


skip_impl = check(
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE__SPEAK__NP_YOURS,
    vote=True,
)(skip_abs)


@tj.as_slash_command('skip', "Skips the current track")
#
@tj.as_message_command('skip', 's', '>>|')
async def skip_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Skips the current song."""
    await skip_impl(ctx, lvc)


# Play at


@tj.with_int_slash_option("position", "Play the track at what position?")
@tj.as_slash_command("play-at", "Plays the track at the specified position")
#
@tj.with_argument('position', converters=int)
@tj.with_parser
@tj.as_message_command('playat', 'play-at', 'pa', 'i', 'pos', 'skipto', '->', '^')
#
@check(Checks.QUEUE | Checks.CONN | Checks.ALONE__SPEAK__CAN_SEEK_ANY, vote=True)
async def play_at_(
    ctx: tj.abc.Context,
    position: int,
    lvc: al.Injected[lv.Lavalink],
):
    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    q.reset_repeat()
    if not (1 <= position <= len(q)):
        await err_say(
            ctx,
            content=f"❌ Invalid position. **The position must be between `1` and `{len(q)}`**",
        )
        return

    async with while_stop(ctx, lvc, d):
        t = q[position - 1]
        q.pos = position - 1
        await lvc.play(ctx.guild_id, t.track).start()
        await set_pause(ctx, lvc, pause=False)

    await say(
        ctx,
        content=f"🎿 Playing the track at position `{position}` (`{t.track.info.title}`)",
    )
    await set_data(ctx.guild_id, lvc, d)


# Next


@tj.as_slash_command('next', "Plays the next track in the queue")
#
@tj.as_message_command('next', 'n')
#
@check(Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE__SPEAK__NP_YOURS)
async def next_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    if not (up := (await get_queue(ctx, lvc)).next):
        await err_say(ctx, content="❗ This is the end of the queue")
        return
    await skip(ctx, lvc, change_stop=False)
    await say(ctx, content=f"⏭️ **`{up.track.info.title}`**")


# Previous


previous_impl = check(
    Checks.CONN | Checks.QUEUE | Checks.ALONE__SPEAK__CAN_SEEK_ANY, vote=True
)(previous_abs)


@tj.as_slash_command('previous', "Plays the previous track in the queue")
#
@tj.as_message_command('previous', 'prev', 'pr', 'prv', 'pre', 'b', 'back', '|<<')
async def previous_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    await previous_impl(ctx, lvc)


# Restart


@tj.as_slash_command('restart', "Restarts the current track; Equivalent to /seek 0:00")
#
@tj.as_message_command('restart', 're', '<')
#
@check(
    Checks.PLAYING
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
    | Checks.PAUSE
)
async def restart_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        if q.is_stopped and (np := q.current):
            await lvc.play(ctx.guild_id, np.track).start()
            q.is_stopped = False

    await seek(ctx, lvc, 0)
    await say(ctx, content=f"◀️ Restarted")


# Seek


@tj.with_str_slash_option(
    'timestamp',
    "Seek to where? (Must be in format such as 2m17s, 4:05)",
    converters=to_ms,
)
@tj.as_slash_command("seek", "Seeks the current track to a timestamp")
#
@tj.with_argument('timestamp', to_ms)
@tj.with_parser
@tj.as_message_command('seek', 'sk', '-v', '-^')
#
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE__SPEAK__NP_YOURS
    | Checks.PAUSE
)
async def seek_(
    ctx: tj.abc.Context,
    timestamp: int,
    lvc: al.Injected[lv.Lavalink],
):
    async with access_queue(ctx, lvc) as q:
        try:
            assert q.np_position is not None
            old_np_ms = q.np_position
            await seek(ctx, lvc, timestamp)
        except IllegalArgument as xe:
            await err_say(
                ctx,
                content=f"❌ Invalid timestamp position given; The track's length is `{to_stamp(xe.arg.expected)}` but was given `{to_stamp(xe.arg.got)}`",
            )
        else:
            await say(
                ctx,
                content=f"🕹️ ~~`{to_stamp(old_np_ms)}`~~ ➜ **`{to_stamp(timestamp)}`**",
            )


# -


loader = playback.load_from_scope().make_loader()
