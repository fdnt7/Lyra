import typing as t

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from ..lib.compose import Binds
from ..lib.playback import while_stop
from ..lib.musicutils import init_component
from ..lib.queue import (
    to_tracks,
    remove_tracks,
    remove_track,
    insert_track,
    shuffle_abs,
    repeat_abs,
    play,
)
from ..lib.utils import (
    EitherContext,
    with_metadata,
    with_message_command_group_template,
    extract_content,
    err_say,
    say,
)
from ..lib.flags import IN_VC_ALONE
from ..lib.compose import (
    Checks,
    with_cmd_composer,
    with_cmd_checks,
)
from ..lib.extras import Option, flatten, fmt_str
from ..lib.lavautils import (
    RepeatMode,
    get_data,
    set_data,
    access_data,
    get_queue,
)
from ..lib.errors import (
    IllegalArgument,
    InvalidArgument,
)


queue = init_component(__name__)


# ~


valid_sources: t.Final = {
    "Youtube": 'yt',
    "Youtube Music": 'ytm',
    "Soundcloud": 'sc',
}


def to_source(value: str, /):
    if value.casefold() not in valid_sources.values():
        valid_sources_fmt = ', '.join(
            ('\"%s\" (%s)' % (j, i) for i, j in valid_sources.items())
        )
        raise ValueError(
            f"Invalid source given. Must be one of the following:\n> {valid_sources_fmt}"
        )
    return value


def to_repeat_mode(value: str, /):
    from ..lib.lavautils import all_repeat_modes

    if value in all_repeat_modes[0]:
        return RepeatMode.NONE
    elif value in all_repeat_modes[1]:
        return RepeatMode.ONE
    elif value in all_repeat_modes[2]:
        return RepeatMode.ALL
    raise ValueError(
        f"Unrecognized repeat mode. Must be one of the following:\n> {fmt_str(flatten(all_repeat_modes))} (got: {value})"
    )


def concat_audio(msg: hk.Message, /, _song: Option[str]):
    audio_files = (
        *filter(
            lambda f: f.media_type and f.media_type.startswith('audio'), msg.attachments
        ),
    )
    if not (_song or audio_files):
        raise tj.NotEnoughArgumentsError(
            "No audio files or search query were given", 'song'
        )
    audio_urls = map(lambda f: f.url, audio_files)
    return (
        ' | '.join(
            (
                _song,
                *audio_urls,
            )
        )
        if _song
        else ' | '.join((*audio_urls,))
    )


COMMON_CHECKS = Checks.QUEUE | Checks.CONN | IN_VC_ALONE

with_common_cmd_check = with_cmd_checks(COMMON_CHECKS)
with_stage_cmd_check = with_cmd_checks(Checks.QUEUE | Checks.CONN | Checks.SPEAK)
with_strict_stage_cmd_check = with_cmd_checks(COMMON_CHECKS | Checks.SPEAK)


# Play


with_play_cmd_check_and_connect_vc = with_cmd_composer(
    Binds.CONNECT_VC, Checks.IN_VC | Checks.SPEAK
)


@with_play_cmd_check_and_connect_vc
@tj.with_bool_slash_option(
    'shuffle',
    "Also shuffles the queue after enqueuing? (If not given, False)",
    default=False,
)
@tj.with_str_slash_option(
    'source',
    "Search from where? (If not given, Youtube)",
    choices=valid_sources,
    default='yt',
)
@tj.with_str_slash_option(
    'song', "What song? [title/direct link, enqueue multiple tracks with \"a | b\"]"
)
@tj.as_slash_command('play', "Plays a song, or add it to the queue")
async def play_s(
    ctx: tj.abc.SlashContext,
    song: str,
    source: str,
    shuffle: bool,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Play a song, or add it to the queue."""
    await _play(ctx, lvc, song, source=source, shuffle=shuffle)


@with_play_cmd_check_and_connect_vc
@tj.with_bool_slash_option(
    'shuffle',
    "Also shuffles the queue after enqueuing? (If not given, False)",
    default=False,
)
@tj.with_attachment_slash_option('audio', "What audio?")
@tj.as_slash_command('play-file', "Plays an attached audio, or add it to the queue")
async def playfile_s(
    ctx: tj.abc.SlashContext,
    audio: hk.Attachment,
    shuffle: bool,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Play a song, or add it to the queue."""
    if not (audio.media_type or '').startswith('audio'):
        raise tj.ConversionError("The attached file is not an audio file", 'audio')
    await _play(ctx, lvc, audio.url, shuffle=shuffle)


@with_play_cmd_check_and_connect_vc
@tj.with_option('source', '--source', '-src', default='yt', converters=to_source)
@tj.with_option(
    'shuffle',
    '--shuffle',
    '-sh',
    default=False,
    empty_value=True,
    converters=tj.to_bool,
)
@tj.with_argument('song', greedy=True, default=None)
@tj.with_parser
#
@tj.as_message_command('play', 'p', 'a', 'add', '+')
async def play_m(
    ctx: tj.abc.MessageContext,
    song: Option[str],
    source: str,
    shuffle: bool,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Play a song, or add it to the queue."""
    _song = concat_audio(ctx.message, song)
    await _play(ctx, lvc, _song, source=source, shuffle=shuffle)


@with_play_cmd_check_and_connect_vc
@with_metadata(handle='play')
@tj.as_message_menu("Enqueue this song")
async def play_c(
    ctx: tj.abc.MenuContext,
    msg: hk.Message,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    cnt = extract_content(msg)
    song = concat_audio(msg, cnt)
    await _play(ctx, lvc, song, source='yt', shuffle=False)


async def _play(
    ctx: EitherContext,
    lvc: lv.Lavalink,
    /,
    song: str,
    *,
    source: Option[str] = None,
    shuffle: bool,
) -> None:
    """Attempts to play the song from youtube."""
    assert ctx.guild_id

    tracks = await to_tracks(ctx, lvc, song, source=source)
    await play(ctx, lvc, tracks, respond=True, shuffle=shuffle)


## Remove


remove_g_s = queue.with_slash_command(
    tj.slash_command_group('remove', "Removes tracks from the queue")
)


@tj.as_message_command_group('remove', 'rem', 'rm', 'rmv', 'del', 'd', '-', strict=True)
@with_message_command_group_template
async def remove_g_m(_: tj.abc.MessageContext):
    """Removes tracks from the queue"""
    ...


## Remove One


@remove_g_s.with_command
@with_stage_cmd_check
@tj.with_str_slash_option(
    'track',
    "The track by the name/position what? (If not given, the current track)",
    default=None,
)
@tj.as_slash_command(
    'one', "Removes a track from the queue by queue position or track name"
)
# -
@remove_g_m.with_command
@with_stage_cmd_check
@tj.with_greedy_argument('track', default=None)
@tj.with_parser
@tj.as_message_command('one', '1', 'o', 's', '.', '^')
async def remove_one_(
    ctx: tj.abc.Context,
    track: Option[str],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    assert ctx.guild_id

    try:
        rm = await remove_track(ctx, track, lvc)
    except InvalidArgument:
        await err_say(
            ctx,
            content=f"❌ Please specify a track to remove or have a track playing first",
        )
    except IllegalArgument as xe:
        arg_exp = xe.arg.expected
        await err_say(
            ctx,
            content=f"❌ Invalid position. **The track position must be between `{arg_exp[0]}` and `{arg_exp[1]}`**",
        )
    else:
        await say(
            ctx, content=f"**`ー`** Removed `{rm.track.info.title}` from the queue"
        )


## Remove Bulk


@remove_g_s.with_command
@with_strict_stage_cmd_check
@tj.with_int_slash_option(
    'end',
    "To what position? (If not given, the end of the queue)",
    default=None,
)
@tj.with_int_slash_option('start', "From what position?")
@tj.as_slash_command(
    'bulk', "Removes a track from the queue by queue position or track name"
)
#
@remove_g_m.with_command
@with_strict_stage_cmd_check
@tj.with_argument('end', converters=int, default=None)
@tj.with_argument('start', converters=int)
@tj.with_parser
@tj.as_message_command('bulk', 'b', 'm', 'r', '<>')
async def remove_bulk_(
    ctx: tj.abc.Context,
    start: int,
    end: Option[int],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    assert ctx.guild_id

    q = await get_queue(ctx, lvc)
    end = end or len(q)
    i_s = start - 1
    t_n = end - i_s

    try:
        await remove_tracks(ctx, start, end, lvc)
    except IllegalArgument:
        await err_say(
            ctx,
            del_after=6.5,
            content=f"❌ Invalid start position or end position\n**Start position must be smaller or equal to end position *AND* both of them has to be in between 1 and the queue length **",
        )
    else:
        await say(
            ctx,
            content=f"**`≡⁻`** Removed track position `{start}-{end}` `({t_n} tracks)` from the queue",
        )
        if start == 1 and end is None:
            await say(
                ctx,
                hidden=True,
                content="💡 It is best to only remove a part of the queue when using `/remove bulk`. *For clearing the entire queue, use `/clear` instead*",
            )


# Clear


@with_common_cmd_check
@tj.as_slash_command('clear', "Clears the queue; Equivalent to /remove bulk start:1")
#
@with_common_cmd_check
@tj.as_message_command('clear', 'destroy', 'clr', 'c')
async def clear_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    async with access_data(ctx, lvc) as d:
        q = d.queue
        l = len(q)
        async with while_stop(ctx, lvc, d):
            q.clr()
        await say(ctx, content=f"💥 Cleared the queue `({l} tracks)`")


# Shuffle


@tj.as_slash_command('shuffle', "Shuffles the upcoming tracks")
#
@tj.as_message_command('shuffle', 'sh', 'shuf', 'rand', 'rd')
async def shuffle_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    await shuffle_abs(ctx, lvc)


# Move


move_g_s = queue.with_slash_command(
    tj.slash_command_group('move', "Moves the track in the queue")
)


@tj.as_message_command_group('move', 'mv', '=>', strict=True)
@with_message_command_group_template
async def move_g_m(_: tj.abc.MessageContext):
    """Moves the track in the queue"""
    ...


## Move Last


@move_g_s.with_command
@with_stage_cmd_check
@tj.with_int_slash_option(
    'track',
    "Position of the track? (If not given, the current position)",
    default=None,
)
@tj.as_slash_command('last', "Moves the selected track to the end of the queue")
#
@move_g_m.with_command
@with_stage_cmd_check
@tj.with_argument('track', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('last', 'l', '>>')
async def move_last_(
    ctx: tj.abc.Context,
    track: Option[int],
    lvc: al.Injected[lv.Lavalink],
):
    """Moves the selected track to the end of the queue"""
    q = await get_queue(ctx, lvc)
    try:
        mv = await insert_track(ctx, len(q), track, lvc)
    except InvalidArgument:
        await err_say(
            ctx,
            content=f"❌ Please specify a track to move or have a track playing first",
        )
        return

    except IllegalArgument:
        await err_say(
            ctx,
            content=f"❌ Invalid position. **The track position must be between `1` and `{len(q)}`**",
        )
        return

    except ValueError:
        await err_say(ctx, content=f"❗ This track is already at the end of the queue")
        return

    else:
        await say(
            ctx,
            content=f"⏬ Moved track `{mv.track.info.title}` to the end of the queue",
        )


## move swap


@move_g_s.with_command
@with_strict_stage_cmd_check
@tj.with_int_slash_option(
    'second',
    "Position of the second track? (If not given, the current track)",
    default=None,
)
@tj.with_int_slash_option('first', "Position of the first track?")
@tj.as_slash_command('swap', "Swaps positions of two tracks in a queue")
#
@move_g_m.with_command
@with_strict_stage_cmd_check
@tj.with_argument('first', converters=int)
@tj.with_argument('second', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('swap', 'sw', '<>', '<->', '<=>')
async def move_swap_(
    ctx: tj.abc.Context,
    first: int,
    second: Option[int],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Swaps positions of two tracks in a queue
    """
    from .playback import while_stop, set_pause

    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    np = q.current
    if second is None:
        if not np:
            await err_say(
                ctx,
                content=f"❌ Please specify a track to swap or have a track playing first",
            )
            return
        i_2nd = q.pos
    else:
        i_2nd = second - 1

    i_1st = first - 1
    if i_1st == i_2nd:
        await err_say(ctx, content=f"❗ Cannot swap a track with itself")
        return
    if not ((0 <= i_1st < len(q)) and (0 <= i_2nd < len(q))):
        await err_say(
            ctx,
            content=f"❌ Invalid position. **Both tracks' position must be between `1` and `{len(q)}`**",
        )
        return

    q[i_1st], q[i_2nd] = q[i_2nd], q[i_1st]
    q.reset_repeat()
    if q.pos in {i_1st, i_2nd}:
        async with while_stop(ctx, lvc, d):
            swapped = q[i_1st] if q.pos == i_1st else q[i_2nd]
            await set_pause(ctx, lvc, pause=False)
            await lvc.play(ctx.guild_id, swapped.track).start()

    await set_data(ctx.guild_id, lvc, d)

    await say(
        ctx,
        content=f"🔄 Swapped tracks `{q[i_2nd].track.info.title}` and `{q[i_1st].track.info.title}` in the queue",
    )


## Move Insert


@move_g_s.with_command
@with_strict_stage_cmd_check
@tj.with_int_slash_option(
    'track', "Position of the track? (If not given, the current position)", default=None
)
@tj.with_int_slash_option('position', "Where to insert the track?")
@tj.as_slash_command('insert', "Inserts a track in the queue after a new position")
#
@move_g_m.with_command
@with_strict_stage_cmd_check
@tj.with_argument('track', converters=int, default=None)
@tj.with_argument('position', converters=int)
@tj.with_parser
@tj.as_message_command('insert', 'ins', 'i', 'v', '^')
async def move_insert_(
    ctx: tj.abc.Context,
    position: int,
    track: Option[int],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Inserts a track in the queue after a new position
    """

    assert ctx.guild_id

    try:
        mv = await insert_track(ctx, position, track, lvc)
    except ValueError:
        await err_say(ctx, content=f"❗ Cannot insert a track after its own position")
        return
    except InvalidArgument:
        await err_say(
            ctx,
            content=f"❌ Please specify a track to insert or have a track playing first",
        )
        return
    except IllegalArgument as xe:
        expected = xe.arg.expected
        await err_say(
            ctx,
            content=f"❌ Invalid position. **Both insert and track position must be between `{expected[0]}` and `{expected[1]}`**",
        )
        return
    else:
        await say(
            ctx,
            content=f"⤴️ Inserted track `{mv.track.info.title}` at position `{position}`",
        )


# Repeat


with_common_cmd_check_with_vote = with_cmd_composer(Binds.VOTE, COMMON_CHECKS)


@with_common_cmd_check_with_vote
@tj.with_str_slash_option(
    'mode',
    "Which mode? (If not given, will cycle between: All > One > Off)",
    choices={'All': 'all', 'One': 'one', 'Off': 'off'},
    converters=to_repeat_mode,
    default=None,
)
@tj.as_slash_command('repeat', "Select a repeat mode for the queue")
#
@with_common_cmd_check_with_vote
@tj.with_argument('mode', to_repeat_mode, default=None)
@tj.with_parser
@tj.as_message_command('repeat', 'r', 'rep', 'lp', 'rp', 'loop')
async def repeat_(
    ctx: tj.abc.Context,
    mode: Option[RepeatMode],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Select a repeat mode for the queue
    """
    await repeat_abs(ctx, mode, lvc)


# -


loader = queue.load_from_scope().make_loader()
