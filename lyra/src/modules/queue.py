import typing as t
import logging
import difflib as dfflib

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv


from hikari.messages import MessageFlag as msgflag
from src.lib.music import auto_connect_vc, music_h
from src.lib.utils import (
    ButtonBuilderType,
    Contextish,
    EitherContext,
    guild_c,
    get_rest,
    reply,
    err_reply,
    edit_components,
    trigger_thinking,
    with_message_command_group_template,
)
from src.lib.checks import Checks, check, check_others_not_in_vc
from src.lib.extras import NULL, url_regex
from src.lib.lavaimpl import (
    repeat_emojis,
    QueueList,
    RepeatMode,
    get_data,
    set_data,
    access_data,
    get_queue,
    access_queue,
)
from src.lib.errors import (
    IllegalArgument,
    InvalidArgument,
    Argument,
    OthersInVoice,
    PlaybackChangeRefused,
    QueryEmpty,
)
from src.lib.consts import LOG_PAD


queue = tj.Component(name='Queue', strict=True).add_check(guild_c).set_hooks(music_h)


logger = logging.getLogger(f"{'queue':<{LOG_PAD}}")
logger.setLevel(logging.DEBUG)


VALID_SOURCES = {
    "Youtube": 'yt',
    "Youtube Music": 'ytm',
    "Soundcloud": 'sc',
}


async def play(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    tracks: lv.Tracks,
    respond: bool = False,
    shuffle: bool = False,
) -> None:
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        if tracks.load_type == 'PLAYLIST_LOADED':
            await enqueue_tracks(
                ctx, lvc, tracks=tracks, queue=q, respond=respond, shuffle=shuffle
            )
        else:
            await enqueue_track(
                ctx,
                lvc,
                track=tracks.tracks[0],
                queue=q,
                respond=respond,
                shuffle=shuffle,
            )


async def enqueue_track(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    track: lv.Track,
    queue: QueueList,
    respond: bool = False,
    shuffle: bool = False,
    ignore_stop: bool = False,
) -> None:
    assert ctx.guild_id
    player = lvc.play(ctx.guild_id, track).requester(ctx.author.id).replace(False)
    queue.ext(player.to_track_queue())
    if respond:
        if shuffle:
            await reply(
                ctx,
                content=f"🔀**`＋`** Added `{track.info.title}` and shuffled the queue",
            )
        else:
            await reply(ctx, content=f"**`＋`** Added `{track.info.title}` to the queue")

    if not queue.is_stopped or ignore_stop:
        await player.start()
    if shuffle:
        queue.shuffle()


async def enqueue_tracks(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    tracks: lv.Tracks,
    queue: QueueList,
    respond: bool = False,
    shuffle: bool = False,
) -> None:
    assert ctx.guild_id
    players = tuple(
        lvc.play(ctx.guild_id, t).requester(ctx.author.id).replace(False)
        for t in tracks.tracks
    )
    queue.ext(*map(lambda p: p.to_track_queue(), players))
    if respond:
        if shuffle:
            await reply(
                ctx,
                content=f"🔀**`≡+`** Added `{len(tracks.tracks)} songs` from playlist `{tracks.playlist_info.name}` and shuffled the queue",
            )
        else:
            await reply(
                ctx,
                content=f"**`≡+`** Added `{len(tracks.tracks)} songs` from playlist `{tracks.playlist_info.name}` to the queue",
            )

    player = next(iter(players))
    if not queue.is_stopped:
        await player.start()
    if shuffle:
        queue.shuffle()


async def remove_track(
    ctx: tj.abc.Context, track: t.Optional[str], lvc: lv.Lavalink, /
) -> lv.TrackQueue:
    from .playback import while_stop, skip

    assert ctx.guild_id

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
            q,
            key=lambda t: dfflib.SequenceMatcher(
                None, t.track.info.title, track
            ).ratio(),
        )
        i = q.index(rm)

    try:
        await check_others_not_in_vc(ctx, lvc)
    except OthersInVoice:
        if rm.requester != ctx.author.id:
            raise PlaybackChangeRefused

        # q.is_stopped = False

    if rm == np:
        async with while_stop(ctx, lvc, d):
            await skip(ctx, lvc, advance=False, change_repeat=True)

    if i < q.pos:
        q.pos = max(0, q.pos - 1)
    q.sub(rm)

    logger.info(
        f"In guild {ctx.guild_id} track [{i: >3}+1/{len(q)}] removed: '{rm.track.info.title}'"
    )

    await set_data(ctx.guild_id, lvc, d)
    return rm


async def remove_tracks(
    ctx: tj.abc.Context, start: int, end: int, lvc: lv.Lavalink, /
) -> list[lv.TrackQueue]:
    from .playback import while_stop, set_pause

    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    if not (1 <= start <= end <= len(q)):
        raise IllegalArgument(Argument((start, end), (1, len(q))))

    i_s = start - 1
    i_e = end - 1
    # t_n = end - i_s
    rm = q[i_s:end]
    if q.current in rm:
        q.reset_repeat()
        async with while_stop(ctx, lvc, d):
            if next_t := None if len(q) <= end else q[end]:
                await set_pause(ctx, lvc, pause=False)
                await lvc.play(ctx.guild_id, next_t.track).start()
    if i_s < q.pos:
        q.pos = max(0, i_s + (q.pos - i_e - 1))
    q.sub(*rm)

    logger.info(
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
            show_author=True,
            content=f"🔀 Shuffled the upcoming tracks. `(Track #{q.pos+2}-{len(q)}; {len(q) - q.pos - 1} tracks)`",
        )


async def insert_track(
    ctx: tj.abc.Context, insert: int, track: t.Optional[int], lvc: lv.Lavalink, /
) -> lv.TrackQueue:
    from .playback import back, skip, while_stop

    assert ctx.guild_id

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
        await back(ctx, lvc, advance=False, change_repeat=True)

    elif p_ == t_ < i_:
        async with while_stop(ctx, lvc, d):
            await skip(ctx, lvc, advance=False, change_repeat=True, change_stop=False)

    q[t_] = NULL  # type: ignore
    q.insert(insert, ins)
    q.remove(NullType)  # type: ignore

    await set_data(ctx.guild_id, lvc, d)
    return ins


async def repeat_abs(
    ctx_: Contextish,
    mode: t.Optional[str],
    /,
    *,
    lvc: lv.Lavalink,
) -> None:
    """Select a repeat mode for the queue"""
    async with access_data(ctx_, lvc) as d:
        q = d.queue
        if mode is None:
            modes = (*(m.value for m in RepeatMode),)
            mode = modes[(modes.index(q.repeat_mode.value) + 1) % 3]
            assert mode is not None
        m = q.set_repeat(mode)

    if m is RepeatMode.NONE:
        msg = "Disabled repeat"
        e = '➡️'
    elif m is RepeatMode.ALL:
        msg = "Repeating the entire queue"
        e = '🔁'
    elif m is RepeatMode.ONE:
        msg = "Repeating only this current track"
        e = '🔂'
    else:
        raise NotImplementedError

    from src.lib.lavaimpl import get_repeat_emoji

    await reply(ctx_, show_author=True, content=f"{e} {msg}")
    if d.nowplaying_msg:
        rest = get_rest(ctx_)

        edits: t.Callable[
            [ButtonBuilderType], ButtonBuilderType
        ] = lambda x: x.set_emoji(get_repeat_emoji(q))
        predicates: t.Callable[[ButtonBuilderType], bool] = (
            lambda x: x.emoji in repeat_emojis
        )

        assert d.nowplaying_components
        components = edit_components(
            rest,
            *d.nowplaying_components,
            edits=edits,
            predicates=predicates,
        )

        await d.edit_now_playing_components(rest, components)


# ~


# Play


@queue.with_slash_command
@tj.with_bool_slash_option(
    'shuffle',
    "Also shuffles the queue after enqueuing? (If not given, False)",
    default=False,
)
@tj.with_str_slash_option(
    'source',
    "Search from where? (If not given, Youtube)",
    choices=VALID_SOURCES,
    default='yt',
)
@tj.with_str_slash_option('song', "What song? [Could be a title or a direct link]")
@tj.as_slash_command('play', "Plays a song, or add it to the queue")
async def play_s(
    ctx: tj.abc.SlashContext,
    song: str,
    source: str,
    shuffle: bool,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    if not url_regex.fullmatch(song):
        song = '%ssearch:%s' % (source, song)

    await _play(ctx, song, shuffle, lvc=lvc)


@queue.with_menu_command
@tj.as_message_menu("Enqueue this song")
async def play_c(
    ctx: tj.abc.MenuContext,
    msg: hk.Message,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    assert msg.content
    if not msg.content:
        assert msg.guild_id
        await err_reply(ctx, content="❌ Cannot process an empty message")
        return
    song = msg.content.strip("<>|")
    if not url_regex.fullmatch(song):
        song = 'ytsearch:%s' % song

    await _play(ctx, song, False, lvc=lvc)


@queue.with_message_command
@tj.with_option('source', '--source', '--src', default='yt')
@tj.with_option('shuffle', '--shuffle', '--sh', default=False, empty_value=True)
@tj.with_greedy_argument('song')
@tj.with_parser
@tj.as_message_command('play', 'p', 'a', 'add', '+')
async def play_m(
    ctx: tj.abc.MessageContext,
    song: str,
    source: str,
    shuffle: bool,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Play a song, or add it to the queue."""

    song = song.strip("<>|")
    await ctx.message.edit(flags=msgflag.SUPPRESS_EMBEDS)
    if source not in VALID_SOURCES.values():
        await err_reply(
            ctx,
            content=f"❗ Invalid source given. Must be one of the following:\n> {', '.join(('`%s (%s)`' % (j, i) for i,j in VALID_SOURCES.items()))}",
        )
        return

    if not url_regex.fullmatch(song):
        song = '%ssearch:%s' % (source, song)

    await _play(ctx, song, shuffle, lvc=lvc)


@auto_connect_vc
@check(Checks.IN_VC | Checks.SPEAK)
async def _play(
    ctx: EitherContext, song: str, shuffle: bool, /, *, lvc: lv.Lavalink
) -> None:
    """Attempts to play the song from youtube."""
    assert ctx.guild_id

    async with trigger_thinking(ctx):
        query = await lvc.get_tracks(song)
    if not query.tracks:
        raise QueryEmpty

    try:
        await play(ctx, lvc, tracks=query, respond=True, shuffle=shuffle)
    except lv.NoSessionPresent:
        # Occurs if lavalink crashes
        await err_reply(
            ctx,
            content="⁉️ Something internal went wrong. Please try again in few minutes",
        )
        return


## Remove


remove_g_s = queue.with_slash_command(
    tj.slash_command_group('remove', "Removes tracks from the queue")
)


@queue.with_message_command
@tj.as_message_command_group('remove', 'rem', 'rm', 'rmv', 'del', 'd', '-', strict=True)
@with_message_command_group_template
async def remove_g_m(_: tj.abc.MessageContext):
    """Removes tracks from the queue"""
    ...


## Remove One


@remove_g_s.with_command
@tj.with_str_slash_option(
    'track',
    "The track by the name/position what? (If not given, the current track)",
    default=None,
)
@tj.as_slash_command(
    'one', "Removes a track from the queue by queue position or track name"
)
async def remove_one_s(
    ctx: tj.abc.SlashContext,
    track: t.Optional[str],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    await _remove_one(ctx, track, lvc=lvc)


@remove_g_m.with_command
@tj.with_greedy_argument('track', default=None)
@tj.with_parser
@tj.as_message_command('one', '1', 'o', 's', '.', '^')
async def remove_one_m(
    ctx: tj.abc.MessageContext,
    track: t.Optional[str],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    await _remove_one(ctx, track, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.SPEAK)
async def _remove_one(
    ctx: tj.abc.Context, track: t.Optional[str], /, *, lvc: lv.Lavalink
):
    assert ctx.guild_id

    try:
        rm = await remove_track(ctx, track, lvc)
    except InvalidArgument:
        await err_reply(
            ctx,
            content=f"❌ Please specify a track to remove or have a track playing first",
        )
    except IllegalArgument[tuple[int, ...]] as xe:
        arg_exp = xe.arg.expected
        await err_reply(
            ctx,
            content=f"❌ Invalid position. **The track position must be between `{arg_exp[0]}` and `{arg_exp[1]}`**",
        )
    else:
        await reply(
            ctx, content=f"**`ー`** Removed `{rm.track.info.title}` from the queue"
        )


## Remove Bulk


@remove_g_s.with_command
@tj.with_int_slash_option(
    'end',
    "To what position? (If not given, the end of the queue)",
    default=None,
)
@tj.with_int_slash_option('start', "From what position?")
@tj.as_slash_command(
    'bulk', "Removes a track from the queue by queue position or track name"
)
async def remove_bulk_s(
    ctx: tj.abc.SlashContext,
    start: int,
    end: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    await _remove_bulk(ctx, start, end, lvc=lvc)


@remove_g_m.with_command
@tj.with_argument('end', converters=int, default=None)
@tj.with_argument('start', converters=int)
@tj.with_parser
@tj.as_message_command('bulk', 'b', 'm', 'r', '<>')
async def remove_bulk_m(
    ctx: tj.abc.MessageContext,
    start: int,
    end: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    await _remove_bulk(ctx, start, end, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.SPEAK | Checks.IN_VC_ALONE)
async def _remove_bulk(
    ctx: tj.abc.Context, start: int, end: t.Optional[int], /, *, lvc: lv.Lavalink
):
    assert ctx.guild_id

    q = await get_queue(ctx, lvc)
    end = end or len(q)
    i_s = start - 1
    t_n = end - i_s

    try:
        await remove_tracks(ctx, start, end, lvc)
    except IllegalArgument:
        await err_reply(
            ctx,
            del_after=6.5,
            content=f"❌ Invalid start position or end position\n**Start position must be smaller or equal to end position *AND* both of them has to be in between 1 and the queue length **",
        )
    else:
        await reply(
            ctx,
            content=f"`≡⁻` Removed track position `{start}-{end}` `({t_n} tracks)` from the queue",
        )
        if start == 1 and end is None:
            await reply(
                ctx,
                hidden=True,
                content="💡 It is best to only remove a part of the queue when using `/remove bulk`. *For clearing the entire queue, use `/clear` instead*",
            )


# Clear


@tj.as_slash_command('clear', "Clears the queue; Equivalent to /remove bulk start:1")
#
@tj.as_message_command('clear', 'destroy', 'clr', 'c')
async def clear(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    await _clear(ctx, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def _clear(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    from .playback import while_stop

    async with access_data(ctx, lvc) as d:
        q = d.queue
        l = len(q)
        async with while_stop(ctx, lvc, d):
            q.clr()
        await reply(ctx, content=f"💥 Cleared the queue `({l} tracks)`")
        return


# Shuffle


@tj.as_slash_command('shuffle', "Shuffles the upcoming tracks")
#
@tj.as_message_command('shuffle', 'sh', 'shuf', 'rand', 'rd')
async def shuffle_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    await shuffle_impl(ctx, lvc=lvc)


# Move


move_g_s = queue.with_slash_command(
    tj.slash_command_group('move', "Moves the track in the queue")
)


@queue.with_message_command
@tj.as_message_command_group('move', 'mv', '=>', strict=True)
@with_message_command_group_template
async def move_g_m(_: tj.abc.MessageContext):
    """Moves the track in the queue"""
    ...


## Move Last


@move_g_s.with_command
@tj.with_int_slash_option(
    'track',
    "Position of the track? (If not given, the current position)",
    default=None,
)
@tj.as_slash_command('last', "Moves the selected track to the end of the queue")
async def move_last_s(
    ctx: tj.abc.SlashContext,
    track: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
):
    await _move_last(ctx, track, lvc=lvc)


@move_g_m.with_command
@tj.with_argument('track', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('last', 'l', '>>')
async def move_last_m(
    ctx: tj.abc.MessageContext,
    track: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Moves the selected track to the end of the queue
    """
    await _move_last(ctx, track, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.SPEAK)
async def _move_last(
    ctx: tj.abc.Context, track: t.Optional[int], /, *, lvc: lv.Lavalink
) -> None:
    """Moves the selected track to the end of the queue"""
    q = await get_queue(ctx, lvc)
    try:
        mv = await insert_track(ctx, len(q), track, lvc)
    except InvalidArgument:
        await err_reply(
            ctx,
            content=f"❌ Please specify a track to move or have a track playing first",
        )
        return

    except IllegalArgument:
        await err_reply(
            ctx,
            content=f"❌ Invalid position. **The track position must be between `1` and `{len(q)}`**",
        )
        return

    except ValueError:
        await err_reply(ctx, content=f"❗ This track is already at the end of the queue")
        return

    else:
        await reply(
            ctx,
            content=f"⏬ Moved track `{mv.track.info.title}` to the end of the queue",
        )


## move swap


@move_g_s.with_command
@tj.with_int_slash_option(
    'second',
    "Position of the second track? (If not given, the current track)",
    default=None,
)
@tj.with_int_slash_option('first', "Position of the first track?")
@tj.as_slash_command('swap', "Swaps positions of two tracks in a queue")
async def move_swap_s(
    ctx: tj.abc.SlashContext,
    first: int,
    second: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
):
    await _move_swap(ctx, first, second, lvc=lvc)


@move_g_m.with_command
@tj.with_argument('first', converters=int)
@tj.with_argument('second', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('swap', 'sw', '<>', '<->', '<=>')
async def move_swap_m(
    ctx: tj.abc.MessageContext,
    first: int,
    second: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Swaps positions of two tracks in a queue
    """
    await _move_swap(ctx, first, second, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.SPEAK | Checks.IN_VC_ALONE)
async def _move_swap(
    ctx: tj.abc.Context, first: int, second: t.Optional[int], /, *, lvc: lv.Lavalink
) -> None:
    """Swaps positions of two tracks in a queue"""
    from .playback import while_stop, set_pause

    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    np = q.current
    if second is None:
        if not np:
            await err_reply(
                ctx,
                content=f"❌ Please specify a track to swap or have a track playing first",
            )
            return
        i_2nd = q.pos
    else:
        i_2nd = second - 1

    i_1st = first - 1
    if i_1st == i_2nd:
        await err_reply(ctx, content=f"❗ Cannot swap a track with itself")
        return
    if not ((0 <= i_1st < len(q)) and (0 <= i_2nd < len(q))):
        await err_reply(
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

    await reply(
        ctx,
        content=f"🔄 Swapped tracks `{q[i_2nd].track.info.title}` and `{q[i_1st].track.info.title}` in the queue",
    )


## Move Insert


@move_g_s.with_command
@tj.with_int_slash_option(
    'track', "Position of the track? (If not given, the current position)", default=None
)
@tj.with_int_slash_option('position', "Where to insert the track?")
@tj.as_slash_command('insert', "Inserts a track in the queue after a new position")
async def move_insert_s(
    ctx: tj.abc.SlashContext,
    position: int,
    track: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
):
    await _move_insert(ctx, position, track, lvc=lvc)


@move_g_m.with_command
@tj.with_argument('track', converters=int, default=None)
@tj.with_argument('position', converters=int)
@tj.with_parser
@tj.as_message_command('insert', 'ins', 'i', 'v', '^')
async def move_insert_m(
    ctx: tj.abc.MessageContext,
    position: int,
    track: t.Optional[int],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Inserts a track in the queue after a new position
    """
    await _move_insert(ctx, position, track, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.SPEAK | Checks.IN_VC_ALONE)
async def _move_insert(
    ctx: tj.abc.Context, position: int, track: t.Optional[int], /, *, lvc: lv.Lavalink
) -> None:
    """Inserts a track in the queue after a new position"""
    assert ctx.guild_id

    try:
        mv = await insert_track(ctx, position, track, lvc)
    except ValueError:
        await err_reply(ctx, content=f"❗ Cannot insert a track after its own position")
        return
    except InvalidArgument:
        await err_reply(
            ctx,
            content=f"❌ Please specify a track to insert or have a track playing first",
        )
        return
    except IllegalArgument[tuple[int, ...]] as xe:
        expected = xe.arg.expected
        await err_reply(
            ctx,
            content=f"❌ Invalid position. **Both insert and track position must be between `{expected[0]}` and `{expected[1]}`**",
        )
        return
    else:
        await reply(
            ctx,
            content=f"⤴️ Inserted track `{mv.track.info.title}` at position `{position}`",
        )


# Repeat


repeat_impl = check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE, vote=True)(
    repeat_abs
)


@queue.with_slash_command
@tj.with_str_slash_option(
    'mode',
    "Which mode? (If not given, will cycle between: All > One > Off)",
    choices={'All': 'all', 'One': 'one', 'Off': 'off'},
    default=None,
)
@tj.as_slash_command('repeat', "Select a repeat mode for the queue")
async def repeat_s(
    ctx: tj.abc.SlashContext,
    mode: t.Optional[str],
    lvc: al.Injected[lv.Lavalink],
):
    await repeat_impl(ctx, mode, lvc=lvc)


@queue.with_message_command
@tj.with_argument('mode', default=None)
@tj.with_parser
@tj.as_message_command('repeat', 'r', 'rep', 'lp', 'rp', 'loop')
async def repeat_m(
    ctx: tj.abc.MessageContext,
    mode: t.Optional[str],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Select a repeat mode for the queue
    """
    if mode:
        mode = mode.lower()
        from src.lib.lavaimpl import all_repeat_modes

        if mode not in all_repeat_modes:
            await err_reply(
                ctx,
                content=f"❗ Unrecognized repeat mode; Must be one of the following: `[{', '.join(all_repeat_modes)}]` `(got: {mode})`",
            )
            return

    await repeat_impl(ctx, mode, lvc=lvc)


# -


loader = queue.load_from_scope().make_loader()
