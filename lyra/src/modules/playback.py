import functools as ft

import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from ..lib.compose import Binds
from ..lib.musicutils import init_component
from ..lib.extras import to_stamp, to_ms
from ..lib.compose import (
    with_cmd_composer,
    with_cmd_checks,
)
from ..lib.flags import (
    ALONE__SPEAK__CAN_SEEK_ANY,
    ALONE__SPEAK__NP_YOURS,
    Checks,
)
from ..lib.errors import (
    IllegalArgument,
)
from ..lib.lavautils import (
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
    say,
    err_say,
)


playback = init_component(__name__)


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


# Play-Pause


@with_common_cmd_check
@tj.as_slash_command(
    'play-pause', "Toggles the playback of the current song between play and pause"
)
#
@with_common_cmd_check
@tj.as_message_command('play-pause', 'playpause', 'pp', '>||')
async def play_pause_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Pauses the current song."""
    await play_pause_abs(ctx, lvc)


# Pause


@with_common_cmd_check
@tj.as_slash_command('pause', "Pauses the current song")
#
@with_common_cmd_check
@tj.as_message_command('pause', '>', 'ps')
async def pause_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Pauses the current song."""
    assert ctx.guild_id

    await set_pause_part(ctx, lvc, pause=True)


# Resume


@with_common_cmd_check
@tj.as_slash_command("resume", "Resumes the current track")
#
@with_common_cmd_check
@tj.as_message_command('resume', 'res', 'rs', '||')
async def resume_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Resumes the current song."""
    assert not ((ctx.guild_id is None) or (ctx.member is None))

    await set_pause_part(ctx, lvc, pause=False)


# Stop


@with_common_cmd_check
@tj.as_slash_command('stop', "Stops the current track; skip to play again")
#
@with_common_cmd_check
@tj.as_message_command('stop', 'st', '[]')
async def stop_(
    ctx: tj.abc.MessageContext,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Stops the currently playing song."""
    await stop(ctx, lvc)
    await say(ctx, content="⏹️ Stopped")


# Fast-forward


@with_activity_cmd_check
@tj.with_float_slash_option(
    'seconds', "Fast-foward by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command('fast-forward', "Fast-forwards the current track")
#
@with_activity_cmd_check
@tj.with_argument('seconds', converters=float, default=10.0)
@tj.with_parser
@tj.as_message_command(
    'fast-forward', 'fastforward', 'forward', 'fw', 'fwd', 'ff', '>>'
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


@with_activity_cmd_check
@tj.with_float_slash_option(
    'seconds', "Rewind by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command('rewind', "Rewinds the current track")
#
@with_activity_cmd_check
@tj.with_argument('seconds', converters=float, default=10.00)
@tj.with_parser
@tj.as_message_command('rewind', 'rw', 'rew', '<<')
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


with_skip_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE, Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS
)


@with_skip_cmd_check_and_voting
@tj.as_slash_command('skip', "Skips the current track")
#
@with_skip_cmd_check_and_voting
@tj.as_message_command('skip', 's', '>>|')
async def skip_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Skips the current song."""
    await skip_abs(ctx, lvc)


# Play at


with_playat_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE, Checks.QUEUE | Checks.CONN | ALONE__SPEAK__CAN_SEEK_ANY
)


@with_playat_cmd_check_and_voting
@tj.with_int_slash_option("position", "Play the track at what position?")
@tj.as_slash_command("play-at", "Plays the track at the specified position")
#
@with_playat_cmd_check_and_voting
@tj.with_argument('position', converters=int)
@tj.with_parser
@tj.as_message_command('play-at', 'playat', 'pa', 'i', 'pos', 'skipto', '->', '^')
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


with_next_cmd_check = with_cmd_checks(
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS
)


@with_next_cmd_check
@tj.as_slash_command('next', "Plays the next track in the queue")
#
@with_next_cmd_check
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


# Previous


with_prev_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE, Checks.CONN | Checks.QUEUE | ALONE__SPEAK__CAN_SEEK_ANY
)


@with_prev_cmd_check_and_voting
@tj.as_slash_command('previous', "Plays the previous track in the queue")
#
@with_prev_cmd_check_and_voting
@tj.as_message_command('previous', 'prev', 'pr', 'prv', 'pre', 'b', 'back', '|<<')
async def previous_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    await previous_abs(ctx, lvc)


# Restart


with_re_cmd_check_and_voting = with_cmd_composer(
    Binds.VOTE,
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS | Checks.PAUSE,
)


@with_re_cmd_check_and_voting
@tj.as_slash_command('restart', "Restarts the current track; Equivalent to /seek 0:00")
#
@with_re_cmd_check_and_voting
@tj.as_message_command('restart', 're', '<')
async def restart_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        if q.is_stopped and (np := q.current):
            await lvc.play(ctx.guild_id, np.track).start()
            q.is_stopped = False

    await seek(ctx, lvc, 0)
    await say(ctx, content=f"◀️ Restarted")


# Seek


@with_activity_cmd_check
@tj.with_str_slash_option(
    'timestamp',
    "Seek to where? (Must be in format such as 2m17s, 4:05)",
    converters=to_ms,
)
@tj.as_slash_command("seek", "Seeks the current track to a timestamp")
#
@with_activity_cmd_check
@tj.with_argument('timestamp', to_ms)
@tj.with_parser
@tj.as_message_command('seek', 'sk', '-v', '-^')
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
