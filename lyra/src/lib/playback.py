import typing as t
import asyncio
import contextlib as ctxlib

import tanjun as tj
import lavasnek_rs as lv

from .consts import STOP_REFRESH
from .extras import Option, Result, Panic
from .utils import (
    ButtonBuilderType,
    Contextish,
    EmojiRefs,
    GuildOrInferable,
    GuildOrRESTInferable,
    RESTInferable,
    edit_components,
    err_say,
    get_client,
    get_rest,
    infer_guild,
    say,
)
from .errors import Argument, IllegalArgument, NotPlaying, QueueEmpty, TrackStopped
from .lavautils import (
    NodeData,
    RepeatMode,
    access_data,
    access_queue,
    get_data,
    get_queue,
    set_data,
)


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
    pause: Option[bool],
    respond: bool = False,
    strict: bool = False,
    update_controller: bool = False,
) -> Panic[bool]:
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
            return False
        if pause is None:
            pause = not q.is_paused
        if pause and q.is_paused:
            if respond:
                await err_say(g_r_inf, content="❗ Already paused")
            return False
        if not (pause or q.is_paused):
            if respond:
                await err_say(g_r_inf, content="❗ Already resumed")
            return False

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
                assert d.out_channel_id
                await say(g_r_inf, channel=d.out_channel_id)

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
        return False
    return True


async def skip(
    g_inf: GuildOrInferable,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    reset_repeat: bool = False,
    change_stop: bool = True,
) -> Option[lv.TrackQueue]:
    async with access_queue(g_inf, lvc) as q:
        skip = q.current
        if reset_repeat:
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
    skip_t = await skip(ctx_, lvc, reset_repeat=True)

    assert skip_t is not None
    await say(ctx_, show_author=True, content=f"⏭️ ~~`{skip_t.track.info.title}`~~")


async def back(
    ctx_: Contextish,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    reset_repeat: bool = False,
) -> lv.TrackQueue:
    async with access_data(ctx_, lvc) as d:
        q = d.queue
        i = q.pos
        if reset_repeat:
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


async def seek(ctx: tj.abc.Context, lvc: lv.Lavalink, total_ms: int, /) -> Result[int]:
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
