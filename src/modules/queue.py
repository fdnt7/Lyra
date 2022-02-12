from src.lib.music import *
from src.lib.checks import Checks, check


queue = tj.Component(name='Queue').add_check(guild_c).set_hooks(music_h)


# Play


@queue.with_slash_command
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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    if not URL_REGEX.fullmatch(song):
        song = '%ssearch:%s' % (source, song)

    await play_(ctx, song, lvc=lvc)


@queue.with_message_command
@tj.with_option('source', '--source', '--src', default='yt')
@tj.with_greedy_argument('song')
@tj.with_parser
@tj.as_message_command('play', 'p', 'a', 'add', '+')
async def play_m(
    ctx: tj.abc.MessageContext,
    song: str,
    source: str,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
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

    if not URL_REGEX.fullmatch(song):
        song = '%ssearch:%s' % (source, song)

    await play_(ctx, song, lvc=lvc)


@attempt_to_connect
@check(Checks.IN_VC)
async def play_(ctx: tj.abc.Context, song: str, /, *, lvc: lv.Lavalink) -> None:
    """Attempts to play the song from youtube."""
    assert ctx.guild_id is not None

    async with trigger_thinking(ctx):
        query = await lvc.get_tracks(song)
    if not query.tracks:
        raise QueryEmpty

    try:
        await play__(ctx, lvc, tracks=query, respond=True)
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
async def remove_g_m(ctx: tj.abc.MessageContext):
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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await remove_one_(ctx, track, lvc=lvc)


@remove_g_m.with_command
@tj.with_greedy_argument('track', default=None)
@tj.with_parser
@tj.as_message_command('one', '1', 'o', 's', '.', '^')
async def remove_one_m(
    ctx: tj.abc.MessageContext,
    track: t.Optional[str],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await remove_one_(ctx, track, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN)
async def remove_one_(
    ctx: tj.abc.Context, track: t.Optional[str], /, *, lvc: lv.Lavalink
):
    assert ctx.guild_id is not None

    try:
        rm = await remove_track__(ctx, track, lvc)
    except InvalidArgument:
        await err_reply(
            ctx,
            content=f"❌ Please specify a track to remove or have a track playing first",
        )
    except IllegalArgument as xe:
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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await remove_bulk_(ctx, start, end, lvc=lvc)


@remove_g_m.with_command
@tj.with_argument('start', converters=int)
@tj.with_argument('end', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('bulk', 'b', 'm', 'r', '<>')
async def remove_bulk_m(
    ctx: tj.abc.MessageContext,
    start: int,
    end: t.Optional[int],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await remove_bulk_(ctx, start, end, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def remove_bulk_(
    ctx: tj.abc.Context, start: int, end: t.Optional[int], /, *, lvc: lv.Lavalink
):
    assert ctx.guild_id is not None

    q = await get_queue(ctx, lvc)
    end = end or len(q)
    i_s = start - 1
    t_n = end - i_s

    try:
        await remove_tracks__(ctx, start, end, lvc)
    except IllegalArgument:
        await err_reply(
            ctx,
            content=f"❌ Invalid start time or end time\n**Start time must be smaller or equal to end time *AND* both of them has to be in between 1 and the queue length **",
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


@queue.with_command
@tj.as_slash_command('clear', "Clears the queue; Equivalent to /remove bulk start:1")
async def clear_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await clear_(ctx, lvc=lvc)


@queue.with_command
@tj.as_message_command('clear', 'd', 'destroy', 'clr', 'c')
async def clear_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await clear_(ctx, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def clear_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        l = len(q)
        async with while_stop(ctx, lvc, q):
            q.clr()
        await reply(ctx, content=f"💥 Cleared the queue `({l} tracks)`")
        return


# Shuffle


@queue.with_command
@tj.as_slash_command('shuffle', "Shuffles the upcoming tracks")
async def shuffle_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await shuffle_(ctx, lvc=lvc)


@queue.with_command
@tj.as_message_command('shuffle', 'sh', 'shuf', 'rand', 'rd')
async def shuffle_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await shuffle_(ctx, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def shuffle_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        if not q.upcoming:
            await err_reply(ctx, content=f"❗ This is the end of the queue")
            return
        q.shuffle()

        await reply(
            ctx,
            content=f"🔀 Shuffled the upcoming tracks. `(Track #{q.pos+2}-{len(q)}; {len(q) - q.pos - 1} tracks)`",
        )


# Move


move_g_s = queue.with_slash_command(
    tj.slash_command_group('move', "Moves the track in the queue")
)


@queue.with_message_command
@tj.as_message_command_group('move', 'mv', '=>', strict=True)
@with_message_command_group_template
async def move_g_m(ctx: tj.abc.MessageContext):
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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await move_last_(ctx, track, lvc=lvc)


@move_g_m.with_command
@tj.with_argument('track', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('last', 'l', '>>')
async def move_last_m(
    ctx: tj.abc.MessageContext,
    track: t.Optional[int],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    """
    Moves the selected track to the end of the queue
    """
    await move_last_(ctx, track, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN)
async def move_last_(
    ctx: tj.abc.Context, track: t.Optional[int], /, *, lvc: lv.Lavalink
) -> None:
    """Moves the selected track to the end of the queue"""
    q = await get_queue(ctx, lvc)
    try:
        mv = await insert_track__(ctx, len(q), track, lvc)
    except InvalidArgument:
        await err_reply(
            ctx,
            content=f"❌ Please specify a track to move or have a track playing first",
        )
        return

    except IllegalArgument as xe:
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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await move_swap_(ctx, first, second, lvc=lvc)


@move_g_m.with_command
@tj.with_argument('first', converters=int)
@tj.with_argument('second', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('swap', 'sw', '<>', '<->', '<=>')
async def move_swap_m(
    ctx: tj.abc.MessageContext,
    first: int,
    second: t.Optional[int],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    """
    Swaps positions of two tracks in a queue
    """
    await move_swap_(ctx, first, second, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def move_swap_(
    ctx: tj.abc.Context, first: int, second: t.Optional[int], /, *, lvc: lv.Lavalink
) -> None:
    """Swaps positions of two tracks in a queue"""
    assert ctx.guild_id is not None

    q = await get_queue(ctx, lvc)
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
    async with access_queue(ctx, lvc) as q:
        q[i_1st], q[i_2nd] = q[i_2nd], q[i_1st]
        q.reset_repeat()
        if q.pos in {i_1st, i_2nd}:
            async with while_stop(ctx, lvc, q):
                swapped = q[i_1st] if q.pos == i_1st else q[i_2nd]
                await set_pause__(ctx, lvc, pause=False)
                await lvc.play(ctx.guild_id, swapped.track).start()

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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await move_insert_(ctx, position, track, lvc=lvc)


@move_g_m.with_command
@tj.with_argument('position', converters=int)
@tj.with_argument('track', converters=int, default=None)
@tj.with_parser
@tj.as_message_command('insert', 'ins', 'i', 'v', '^')
async def move_insert_m(
    ctx: tj.abc.MessageContext,
    position: int,
    track: t.Optional[int],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    """
    Inserts a track in the queue after a new position
    """
    await move_insert_(ctx, position, track, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def move_insert_(
    ctx: tj.abc.Context, position: int, track: t.Optional[int], /, *, lvc: lv.Lavalink
) -> None:
    """Inserts a track in the queue after a new position"""
    assert ctx.guild_id is not None

    try:
        mv = await insert_track__(ctx, position, track, lvc)
    except ValueError:
        await err_reply(ctx, content=f"❗ Cannot insert a track after its own position")
        return
    except InvalidArgument:
        await err_reply(
            ctx,
            content=f"❌ Please specify a track to insert or have a track playing first",
        )
        return
    except IllegalArgument as xe:
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
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await repeat_(ctx, mode, lvc=lvc)


@queue.with_message_command
@tj.with_argument('mode', default=None)
@tj.with_parser
@tj.as_message_command('repeat', 'r', 'lp', 'rp', 'loop')
async def repeat_m(
    ctx: tj.abc.MessageContext,
    mode: t.Optional[str],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    """
    Select a repeat mode for the queue
    """
    if mode:
        mode = mode.lower()
        from src.lib.lavaimpl import REPEAT_MODES_ALL

        if mode not in REPEAT_MODES_ALL:
            await err_reply(
                ctx,
                content=f"❗ Unrecognized repeat mode; Must be one of the following: `[{', '.join(REPEAT_MODES_ALL)}]` `(got: {mode})`",
            )
            return

    await repeat_(ctx, mode, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)
async def repeat_(
    ctx: tj.abc.Context, mode: t.Optional[str], /, *, lvc: lv.Lavalink
) -> None:
    """Select a repeat mode for the queue"""
    async with access_queue(ctx, lvc) as q:
        if mode is None:
            modes = tuple(m.value for m in RepeatMode)
            mode = modes[(modes.index(q.repeat_mode.value) + 1) % 3]
            assert mode is not None
        m = q.set_repeat(mode)

    match m:
        case RepeatMode.NONE:
            mes = "➡️ Disabled repeat"
        case RepeatMode.ALL:
            mes = "🔁 Repeating the entire queue"
        case RepeatMode.ONE:
            mes = "🔂 Repeating only this current track"
        case _:
            raise NotImplementedError

    await reply(ctx, content=mes)


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(queue.copy())
