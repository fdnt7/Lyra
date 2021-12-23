from src.lib.music import *


playback = tj.Component(checks=(guild_c,), hooks=music_h)


# Play-Pause


@playback.with_slash_command
@tj.as_slash_command(
    "playpause", "Toggles the playback of the current song between play and pause"
)
async def play_pause_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await play_pause_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("playpause", "pp")
async def play_pause_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Pauses the current song."""
    await play_pause_(ctx, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
)
async def play_pause_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if q.is_paused:
            return await resume_(ctx, lvc=lvc)
        return await pause_(ctx, lvc=lvc)


# Pause


@playback.with_slash_command
@tj.as_slash_command("pause", "Pauses the current song")
async def pause_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await pause_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("pause")
async def pause_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
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
async def pause_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """Pauses the current song."""
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if q.is_paused:
            return await err_reply(ctx, content="❗ Already paused")

        q._last_np_position = q.np_position
        q.is_paused = True
        await lvc.pause(ctx.guild_id)
    await reply(ctx, content="⏸️ Paused")


# Resume


@playback.with_slash_command
@tj.as_slash_command("resume", "Resumes the current track")
async def resume_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await resume_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("resume")
async def resume_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
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
async def resume_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """Resumes playing the current song."""
    assert not ((ctx.guild_id is None) or (ctx.member is None))

    async with access_queue(ctx, lvc) as q:
        if not q.is_paused:
            return await err_reply(ctx, content="❗ Already resumed")

        np_pos = q.np_position
        assert np_pos is not None
        q._last_track_played = curr_time_ms() - np_pos
        q.is_paused = False
        await lvc.resume(ctx.guild_id)
    await reply(ctx, content="▶️ Resumed")


# Stop


@playback.with_slash_command
@tj.as_slash_command("stop", "Stops the current track; skip to play again")
async def stop_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await stop_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("stop")
async def stop_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Stops the currently playing song, skip to play again."""
    await stop_(ctx, lvc=lvc)


# @check_advancability
# @check_activity_song_req_perms
@check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
)
async def stop_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """Stops the currently playing song."""
    await stop__(ctx, lvc)
    await reply(ctx, content="⏹️ Stopped")


# Fast-forward


@playback.with_slash_command
@tj.with_float_slash_option(
    "seconds", "Fast-foward by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command("fastforward", "Fast-forwards the current track")
async def fastforward_s(
    ctx: tj.abc.SlashContext,
    seconds: float,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await fastforward_(ctx, seconds, lvc=lvc)


@playback.with_message_command
@tj.with_argument("seconds", converters=float, default=10.00)
@tj.with_parser
@tj.as_message_command("fastforward", "ff")
async def fastforward_m(
    ctx: tj.abc.MessageContext,
    seconds: float,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
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
async def fastforward_(ctx: tj.abc.Context, seconds: float, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        assert not ((q.now_playing is None) or (q.np_position is None))
        np_info = q.now_playing.track.info
        old_np_ms = q.np_position
        new_np_ms = old_np_ms + int(seconds * 1000)

        try:
            await seek__(ctx, lvc, new_np_ms)
        except IllegalArgument:
            await skip__(ctx, lvc)
            return await reply(
                ctx,
                content=f"❗⏭️ ~~`{np_info.title}`~~ *(The fast-forwarded time was too large; **Skipping** to the next track)*",
            )
        fmt_sec = f"{I if (I := int(seconds)) == seconds else f'{seconds:.3f}'}s"
        await reply(
            ctx,
            content=f"⏩ ~~`{ms_stamp(old_np_ms)}`~~ **❯❯** **`{ms_stamp(new_np_ms)}`** `({fmt_sec})`",
        )


# Rewind


@playback.with_slash_command
@tj.with_float_slash_option(
    "seconds", "Rewind by how much? (If not given, 10 seconds)", default=10.0
)
@tj.as_slash_command("rewind", "Rewinds the current track")
async def rewind_s(
    ctx: tj.abc.SlashContext,
    seconds: float,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await rewind_(ctx, seconds, lvc=lvc)


@playback.with_message_command
@tj.with_argument("seconds", converters=float, default=10.00)
@tj.with_parser
@tj.as_message_command("rewind", "rw")
async def rewind_m(
    ctx: tj.abc.MessageContext,
    seconds: float,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
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
async def rewind_(ctx: tj.abc.Context, seconds: float, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        assert not ((q.now_playing is None) or (q.np_position is None))
        old_np_ms = q.np_position
        new_np_ms = old_np_ms - int(seconds * 1000)

        try:
            await seek__(ctx, lvc, new_np_ms)
        except IllegalArgument:
            await seek__(ctx, lvc, 0)
            return await reply(
                ctx,
                content=f"❗◀️ *The rewinded time was too large; **Restarted** the current track*",
            )
        fmt_sec = f"{I if (I := int(seconds)) == seconds else f'{seconds:.3f}'}s"
        await reply(
            ctx,
            content=f"⏪ **`{ms_stamp(new_np_ms)}`** **❮❮** ~~`{ms_stamp(old_np_ms)}`~~ `({fmt_sec})`",
        )


# Skip


@playback.with_slash_command
@tj.as_slash_command("skip", "Skips the current track")
async def skip_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await skip_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("skip", "s")
async def skip_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Skips the current song."""
    await skip_(ctx, lvc=lvc)


@check(Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CURR_T_YOURS)
async def skip_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """Skips the current song."""
    skip = await skip__(ctx, lvc)

    # if not skip:
    #     return await err_reply(ctx, content="❗ No tracks left to skip.")
    assert skip is not None
    await reply(ctx, content=f"⏭️ ~~`{skip.track.info.title}`~~")


# Play at


@playback.with_slash_command
@tj.with_int_slash_option("position", "Play the track at what position?")
@tj.as_slash_command("playat", "Play the track at the specified position")
async def play_at_s(
    ctx: tj.abc.SlashContext,
    position: int,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await play_at_(ctx, position, lvc=lvc)


@playback.with_message_command
@tj.with_argument("position", converters=int)
@tj.with_parser
@tj.as_message_command("playat", "pa", "i", "pos", "skipto", "st")
async def play_at_m(
    ctx: tj.abc.MessageContext,
    position: int,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await play_at_(ctx, position, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN | Checks.ALONE_OR_CAN_SEEK_QUEUE)
async def play_at_(ctx: tj.abc.Context, position: int, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if not (1 <= position <= len(q)):
            return await err_reply(
                ctx,
                content=f"❌ Invalid position. **The position must be between `1` and `{len(q)}`**",
            )

        async with while_stop(ctx, lvc, q):
            t = q[position - 1]
            q.pos = position - 1
            await lvc.play(ctx.guild_id, t.track).start()

        return await reply(
            ctx,
            content=f"🎿 Playing the track at position `{position}` (`{t.track.info.title}`)",
        )


# Next


@playback.with_slash_command
@tj.as_slash_command("next", "Plays the next track in the queue")
async def next_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await next_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("next", "n")
async def next_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await next_(ctx, lvc=lvc)


@check(Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CURR_T_YOURS)
async def next_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        if not (up := q.upcoming):
            return await err_reply(ctx, content="❗ This is the end of the queue")
        await skip__(ctx, lvc)
        await reply(ctx, content=f"⏭️ **`{up[0].track.info.title}`**")


# Previous


@playback.with_slash_command
@tj.as_slash_command("previous", "Plays the previous track in the queue")
async def previous_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await previous_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("previous", "prev", "pr", "prv", "pre", "b", "back")
async def previous_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await previous_(ctx, lvc=lvc)


@check(Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CAN_SEEK_QUEUE)
async def previous_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if not (prev := q.history):
            return await err_reply(ctx, content="❗ This is the start of the queue")
        async with while_stop(ctx, lvc, q):
            q.decr()

        await lvc.play(ctx.guild_id, prev[-1].track).start()
        await reply(ctx, content=f"⏮️ **`{prev[-1].track.info.title}`**")


# Restart


@playback.with_slash_command
@tj.as_slash_command("restart", "Restarts the current track; Equivalent to /seek 0:00")
async def restart_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await restart_(ctx, lvc=lvc)


@playback.with_message_command
@tj.as_message_command("restart", "re")
async def restart_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await restart_(ctx, lvc=lvc)


@check(
    Checks.PLAYING
    | Checks.CONN
    | Checks.QUEUE
    | Checks.ALONE_OR_CURR_T_YOURS
    | Checks.PAUSE
)
async def restart_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert ctx.guild_id is not None
    async with access_queue(ctx, lvc) as q:
        if q.is_stopped and (np := q.now_playing):
            await lvc.play(ctx.guild_id, np.track).start()
            q.is_stopped = False

    await seek__(ctx, lvc, 0)
    await reply(ctx, content=f"◀️ Restarted")


# Seek


@playback.with_slash_command
@tj.with_str_slash_option(
    "timestamp",
    "Seek to where? (Must be in format such as 2m17s, 4:05)",
)
@tj.as_slash_command("seek", "Seeks the current track to a timestamp")
async def seek_s(
    ctx: tj.abc.SlashContext,
    timestamp: str,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await seek_(ctx, timestamp, lvc=lvc)


@playback.with_message_command
@tj.with_argument("timestamp")
@tj.with_parser
@tj.as_message_command("seek", "sk")
async def seek_m(
    ctx: tj.abc.MessageContext,
    timestamp: str,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
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
async def seek_(ctx: tj.abc.Context, timestamp: str, lvc: lv.Lavalink):
    async with access_queue(ctx, lvc) as q:
        try:
            assert q.np_position is not None
            old_np_ms = q.np_position
            new_np_ms = stamp_ms(timestamp)
            await seek__(ctx, lvc, new_np_ms)
        except InvalidArgument as ie:
            return await err_reply(
                ctx,
                content=f"❌ Invalid timestamp format given; Must be in the following format: `{ie.arg.expected}`",
            )
        except IllegalArgument as xe:
            return await err_reply(
                ctx,
                content=f"❌ Invalid timestamp position given; The track's length is `{ms_stamp(xe.arg.expected)}` but was given `{ms_stamp(xe.arg.got)}`",
            )
        else:
            await reply(
                ctx,
                content=f"🕹️ ~~`{ms_stamp(old_np_ms)}`~~ ➜ **`{ms_stamp(new_np_ms)}`**",
            )


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(playback.copy())
