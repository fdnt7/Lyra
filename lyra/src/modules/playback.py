from src.lib.music import *
from src.lib.checks import Checks, check


playback = (
    tj.Component(name='Playback', strict=True).add_check(guild_c).set_hooks(music_h)
)


# Play-Pause


@tj.as_slash_command(
    'play-pause', "Toggles the playback of the current song between play and pause"
)
#
@tj.as_message_command('playpause', 'play-pause', 'pp', '>||')
async def play_pause(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Pauses the current song."""
    await play_pause_impl(ctx, lvc=lvc)


# Pause


@tj.as_slash_command('pause', "Pauses the current song")
#
@tj.as_message_command('pause', '>', 'ps')
async def pause(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Pauses the current song."""
    await pause_(ctx, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
)
async def pause_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Pauses the current song."""
    assert ctx.guild_id

    await set_pause__(ctx, lvc, pause=True, respond=True, update_controller=True)


# Resume


@tj.as_slash_command("resume", "Resumes the current track")
#
@tj.as_message_command('resume', 'res', 'rs', '||')
async def resume(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Resumes the current song."""
    await resume_(ctx, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
)
async def resume_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Resumes playing the current song."""
    assert not ((ctx.guild_id is None) or (ctx.member is None))

    await set_pause__(ctx, lvc, pause=False, respond=True, update_controller=True)


# Stop


@tj.as_slash_command('stop', "Stops the current track; skip to play again")
#
@tj.as_message_command('stop', 'st', '[]')
async def stop(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Stops the currently playing song, skip to play again."""
    await stop_(ctx, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
)
async def stop_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Stops the currently playing song."""
    await stop__(ctx, lvc)
    await reply(ctx, content="⏹️ Stopped")


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
async def fastforward(
    ctx: tj.abc.MessageContext,
    seconds: float,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
):
    await fastforward_(ctx, seconds, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
    | Checks.PAUSE
)
async def fastforward_(ctx: tj.abc.Context, seconds: float, /, *, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        assert not ((q.current is None) or (q.np_position is None))
        np_info = q.current.track.info
        old_np_ms = q.np_position
        new_np_ms = old_np_ms + int(seconds * 1000)

        try:
            await seek__(ctx, lvc, new_np_ms)
        except IllegalArgument:
            await skip__(ctx, lvc, change_stop=False)
            await reply(
                ctx,
                content=f"❕⏭️ ~~`{np_info.title}`~~ *(The fast-forwarded time was too large; **Skipping** to the next track)*",
            )
        fmt_sec = f"{I if (I := int(seconds)) == seconds else f'{seconds:.3f}'}s"
        await reply(
            ctx,
            content=f"⏩ ~~`{ms_stamp(old_np_ms)}`~~ **❯❯** **`{ms_stamp(new_np_ms)}`** `({fmt_sec})`",
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
async def rewind(
    ctx: tj.abc.Context,
    seconds: float,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
):
    await rewind_(ctx, seconds, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
    | Checks.PAUSE
)
async def rewind_(ctx: tj.abc.Context, seconds: float, /, *, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        assert not ((q.current is None) or (q.np_position is None))
        old_np_ms = q.np_position
        new_np_ms = old_np_ms - int(seconds * 1000)

        try:
            await seek__(ctx, lvc, new_np_ms)
        except IllegalArgument:
            await seek__(ctx, lvc, 0)
            await reply(
                ctx,
                content=f"❕◀️ *The rewinded time was too large; **Restarted** the current track*",
            )
        fmt_sec = f"{I if (I := int(seconds)) == seconds else f'{seconds:.3f}'}s"
        await reply(
            ctx,
            content=f"⏪ **`{ms_stamp(new_np_ms)}`** **❮❮** ~~`{ms_stamp(old_np_ms)}`~~ `({fmt_sec})`",
        )


# Skip


@tj.as_slash_command('skip', "Skips the current track")
#
@tj.as_message_command('skip', 's', '>>|')
async def skip(
    ctx: tj.abc.Context,
    bot: hk.GatewayBot = tj.inject(type=hk.GatewayBot),
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Skips the current song."""
    await check(
        Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CURR_T_YOURS,
        vote=True,
    )(skip_impl)(ctx, bot=bot, lvc=lvc)


# Play at


@tj.with_int_slash_option("position", "Play the track at what position?")
@tj.as_slash_command("play-at", "Plays the track at the specified position")
#
@tj.with_argument('position', converters=int)
@tj.with_parser
@tj.as_message_command('playat', 'play-at', 'pa', 'i', 'pos', 'skipto', '->', '^')
async def play_at(
    ctx: tj.abc.Context,
    position: int,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
):
    await play_at_(ctx, position, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.ALONE_OR_CAN_SEEK_QUEUE)
async def play_at_(ctx: tj.abc.Context, position: int, /, *, lvc: lv.Lavalink):
    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    q.reset_repeat()
    if not (1 <= position <= len(q)):
        await err_reply(
            ctx,
            content=f"❌ Invalid position. **The position must be between `1` and `{len(q)}`**",
        )
        return

    async with while_stop(ctx, lvc, d):
        t = q[position - 1]
        q.pos = position - 1
        await lvc.play(ctx.guild_id, t.track).start()
        await set_pause__(ctx, lvc, pause=False)

    await reply(
        ctx,
        content=f"🎿 Playing the track at position `{position}` (`{t.track.info.title}`)",
    )
    await set_data(ctx.guild_id, lvc, d)


# Next


@tj.as_slash_command('next', "Plays the next track in the queue")
#
@tj.as_message_command('next', 'n')
async def next(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
):
    await next_(ctx, lvc=lvc)


@check(Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CURR_T_YOURS)
async def next_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    if not (up := (await get_queue(ctx, lvc)).next):
        await err_reply(ctx, content="❗ This is the end of the queue")
        return
    await skip__(ctx, lvc, change_stop=False)
    await reply(ctx, content=f"⏭️ **`{up.track.info.title}`**")


# Previous


@tj.as_slash_command('previous', "Plays the previous track in the queue")
#
@tj.as_message_command('previous', 'prev', 'pr', 'prv', 'pre', 'b', 'back', '|<<')
async def previous(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
    bot: hk.GatewayBot = tj.inject(type=hk.GatewayBot),
):
    await check(Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CAN_SEEK_QUEUE, vote=True)(
        previous_impl
    )(ctx, lvc=lvc, bot=bot)


# Restart


@tj.as_slash_command('restart', "Restarts the current track; Equivalent to /seek 0:00")
#
@tj.as_message_command('restart', 're', '<')
async def restart(ctx: tj.abc.Context, lvc: lv.Lavalink = tj.inject(type=lv.Lavalink)):
    await restart_(ctx, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
    | Checks.PAUSE
)
async def restart_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        if q.is_stopped and (np := q.current):
            await lvc.play(ctx.guild_id, np.track).start()
            q.is_stopped = False

    await seek__(ctx, lvc, 0)
    await reply(ctx, content=f"◀️ Restarted")


# Seek


@tj.with_str_slash_option(
    'timestamp',
    "Seek to where? (Must be in format such as 2m17s, 4:05)",
)
@tj.as_slash_command("seek", "Seeks the current track to a timestamp")
#
@tj.with_argument('timestamp')
@tj.with_parser
@tj.as_message_command('seek', 'sk', '-v', '-^')
async def seek(
    ctx: tj.abc.Context,
    timestamp: str,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
):
    await seek_(ctx, timestamp, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
    | Checks.PAUSE
)
async def seek_(ctx: tj.abc.Context, timestamp: str, /, *, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        try:
            assert q.np_position is not None
            old_np_ms = q.np_position
            new_np_ms = stamp_ms(timestamp)
            await seek__(ctx, lvc, new_np_ms)
        except InvalidArgument as ie:
            await err_reply(
                ctx,
                content=f"❌ Invalid timestamp format given; Must be in the following format: `{ie.arg.expected}`",
            )
        except IllegalArgument as xe:
            await err_reply(
                ctx,
                content=f"❌ Invalid timestamp position given; The track's length is `{ms_stamp(xe.arg.expected)}` but was given `{ms_stamp(xe.arg.got)}`",
            )
        else:
            await reply(
                ctx,
                content=f"🕹️ ~~`{ms_stamp(old_np_ms)}`~~ ➜ **`{ms_stamp(new_np_ms)}`**",
            )


# -


loader = playback.load_from_scope().make_loader()
