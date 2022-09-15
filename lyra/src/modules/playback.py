import typing as t
import functools as ft

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv
import tanjun.annotations as ja

from ..lib.cmd.ids import CommandIdentifier as C
from ..lib.cmd.flags import (
    ALONE__SPEAK__CAN_SEEK_ANY,
    ALONE__SPEAK__NP_YOURS,
    Checks,
)
from ..lib.cmd.compose import (
    Binds,
    with_cmd_composer,
    with_cmd_checks,
)
from ..lib.musicutils import __init_component__
from ..lib.extras import to_stamp, to_ms
from ..lib.errors import (
    IllegalArgument,
)
from ..lib.lava.utils import (
    get_data,
    set_data,
    get_queue,
    access_queue,
)
from ..lib.playback import (
    previous_abs,
    set_pause,
    seek,
    skip,
    skip_abs,
    stop,
    while_stop,
)
from ..lib.utils import (
    Option,
    ConnectionInfo,
    say,
    err_say,
    with_annotated_args,
)


playback = __init_component__(__name__)


# ~


set_pause_part = ft.partial(set_pause, respond=True, update_controller=True)

play_pause_abs = ft.partial(set_pause_part, pause=None)

COMMON_CHECKS = (
    Checks.CONN
    | Checks.QUEUE
    | Checks.PLAYING
    | Checks.ADVANCE
    | ALONE__SPEAK__NP_YOURS
)

with_common_cmd_check = with_cmd_checks(COMMON_CHECKS)

with_activity_cmd_check = with_cmd_checks(COMMON_CHECKS | Checks.PAUSE)


@playback.with_listener()
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    client: al.Injected[tj.Client],
    lvc: al.Injected[lv.Lavalink],
    bot: al.Injected[hk.GatewayBot],
):
    def conn():
        return t.cast(
            Option[ConnectionInfo],
            lvc.get_guild_gateway_connection_info(event.guild_id),
        )

    new = event.state
    old = event.old_state

    if not await lvc.get_guild_node(event.guild_id):
        return

    bot_u = bot.get_me()
    assert bot_u

    async def users_in_vc() -> t.Collection[hk.VoiceState]:
        _conn = conn()
        cache = client.cache
        if not _conn:
            return frozenset()
        assert conn is not None and cache
        ch_id: int = _conn['channel_id']
        return (
            await cache.get_voice_states_view_for_channel(event.guild_id, ch_id)
            .iterator()
            .filter(lambda v: not v.member.is_bot)
            .collect(frozenset)
        )

    new_vc_id = new.channel_id
    out_ch = (await get_data(event.guild_id, lvc)).out_channel_id
    assert out_ch

    if not (_conn := conn()):
        return
    assert _conn is not None

    from .playback import set_pause

    old_is_stage = (
        None
        if not (old and old.channel_id)
        else isinstance(
            bot.cache.get_guild_channel(old.channel_id), hk.GuildStageChannel
        )
    )

    if (
        new_vc_id
        and isinstance(bot.cache.get_guild_channel(new_vc_id), hk.GuildStageChannel)
        and new.user_id == bot_u.id
    ):
        old_suppressed = old.is_suppressed if old else True
        old_requested = old.requested_to_speak_at if old else None

        if (
            not old_suppressed
            and new.is_suppressed
            and old_is_stage
            and await set_pause(event, lvc, pause=True, update_controller=True)
        ):
            await client.rest.create_message(
                out_ch,
                f"👥▶️ Paused as the bot was moved to audience",
            )
        elif old_suppressed and not new.is_suppressed:
            await client.rest.create_message(
                out_ch,
                f"🎭🗣️ Became a speaker",
            )
        elif not new.requested_to_speak_at and old_requested:
            await client.rest.create_message(
                out_ch, f"❕🎭 Bot's request to speak was dismissed"
            )

    in_voice = await users_in_vc()
    node_vc_id: int = _conn['channel_id']
    # if new.channel_id == vc and len(in_voice) == 1 and new.user_id != bot_u.id:
    #     # Someone rejoined
    #     try:
    #         await set_pause__(event.guild_id, lvc, pause=False)
    #         await client.rest.create_message(ch, f"✨⏸️ Resumed")
    #     except NotConnected:
    #         pass

    if (
        new_vc_id != node_vc_id
        and not in_voice
        and old
        and old.channel_id == node_vc_id
        and await set_pause(event, lvc, pause=True, update_controller=True)
    ):
        # Everyone left
        await client.rest.create_message(out_ch, f"🕊️▶️ Paused as no one is listening")


# /play-pause


@with_common_cmd_check(C.PLAYPAUSE)
# -
@tj.as_slash_command(
    'play-pause', "Toggles the playback of the current song between play and pause"
)
@tj.as_message_command('play-pause', 'playpause', 'pp', '>||')
async def play_pause_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Pauses the current song."""
    await play_pause_abs(ctx, lvc)


# /pause


@with_common_cmd_check(C.PAUSE)
# -
@tj.as_slash_command('pause', "Pauses the current song")
@tj.as_message_command('pause', '>', 'ps')
async def pause_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Pauses the current song."""
    assert ctx.guild_id

    await set_pause_part(ctx, lvc, pause=True)


# /resume


@with_common_cmd_check(C.RESUME)
# -
@tj.as_slash_command("resume", "Resumes the current track")
@tj.as_message_command('resume', 'res', 'rs', '||')
async def resume_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Resumes the current song."""
    assert not ((ctx.guild_id is None) or (ctx.member is None))

    await set_pause_part(ctx, lvc, pause=False)


# /stop


@with_common_cmd_check(C.STOP)
# -
@tj.as_slash_command('stop', "Stops the current track; skip to play again")
@tj.as_message_command('stop', 'st', '[]')
async def stop_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Stops the currently playing song."""
    await stop(ctx, lvc)
    await say(ctx, content="⏹️ Stopped")


# /fast-forward


# TODO: Use annotation-based option declaration once declaring positional-only argument is possible
@with_activity_cmd_check(C.FASTFORWARD)
# -
@tj.with_float_slash_option(
    'seconds', "Fast-foward by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command('fast-forward', "Fast-forwards the current track")
@tj.with_argument('seconds', converters=float, default=10.0)
@tj.as_message_command(
    'fast-forward', 'fastforward', 'forward', 'fw', 'fwd', 'ff', '>>'
)
async def fastforward_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
    seconds: float,
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


# /rewind


# TODO: Use annotation-based option declaration once declaring positional-only argument is possible
@with_activity_cmd_check(C.REWIND)
# -
@tj.with_float_slash_option(
    'seconds', "Rewind by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command('rewind', "Rewinds the current track")
@tj.with_argument('seconds', converters=float, default=10.00)
@tj.as_message_command('rewind', 'rw', 'rew', '<<')
async def rewind_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    seconds: float,
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


# /skip


with_skip_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE, Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS
)


@with_skip_cmd_check_and_voting(C.SKIP)
# -
@tj.as_slash_command('skip', "Skips the current track")
@tj.as_message_command('skip', 's', '>>|')
async def skip_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Skips the current song."""
    await skip_abs(ctx, lvc)


# /play-at


with_playat_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE, Checks.QUEUE | Checks.CONN | ALONE__SPEAK__CAN_SEEK_ANY
)


@with_annotated_args
@with_playat_cmd_check_and_voting(C.PLAYAT)
# -
@tj.as_slash_command("play-at", "Plays the track at the specified position")
@tj.as_message_command('play-at', 'playat', 'pa', 'i', 'pos', 'skipto', '->', '^')
async def play_at_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    position: t.Annotated[ja.Int, "Play the track at what position?"],
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


# /next


with_next_cmd_check = with_cmd_checks(
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS
)


@with_next_cmd_check(C.NEXT)
# -
@tj.as_slash_command('next', "Plays the next track in the queue")
@tj.as_message_command('next', 'n')
async def next_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    if not (up := (await get_queue(ctx, lvc)).next):
        await err_say(ctx, content="❗ This is the end of the queue")
        return
    await skip(ctx, lvc, change_stop=False)
    await say(ctx, content=f"⏭️ **`{up.track.info.title}`**")


# /previous


with_prev_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE, Checks.CONN | Checks.QUEUE | ALONE__SPEAK__CAN_SEEK_ANY
)


@with_prev_cmd_check_and_voting(C.PREVIOUS)
# -
@tj.as_slash_command('previous', "Plays the previous track in the queue")
@tj.as_message_command('previous', 'prev', 'pr', 'prv', 'pre', 'b', 'back', '|<<')
async def previous_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    await previous_abs(ctx, lvc)


# /restart


with_re_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE,
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS | Checks.PAUSE,
)


@with_re_cmd_check_and_voting(C.RESTART)
# -
@tj.as_slash_command('restart', "Restarts the current track; Equivalent to /seek 0:00")
@tj.as_message_command('restart', 're', '<')
async def restart_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        if q.is_stopped and (np := q.current):
            await lvc.play(ctx.guild_id, np.track).start()
            q.is_stopped = False

    await seek(ctx, lvc, 0)
    await say(ctx, content=f"◀️ Restarted")


# /seek


@with_annotated_args
@with_activity_cmd_check(C.SEEK)
# -
@tj.as_slash_command("seek", "Seeks the current track to a timestamp")
@tj.as_message_command('seek', 'sk', '-v', '-^')
async def seek_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    timestamp: t.Annotated[
        ja.Converted[to_ms], "Seek to where? (Must be in format such as 2m17s, 4:05)"
    ],
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
