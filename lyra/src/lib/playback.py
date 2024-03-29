import asyncio
import contextlib as ctxlib

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from .consts import TIMEOUT
from .extras import Option, Fallible, Panic, MapSig, PredicateSig
from .errors import (
    Argument,
    IllegalArgumentError,
    QueueEmptyError,
    NotPlayingError,
    TrackStoppedError,
)
from .utils import (
    IntCastable,
    MaybeGuildIDAware,
    ButtonBuilderType,
    ContextishType,
    RESTAwareType,
    EmojiCache,
    edit_components,
    err_say,
    get_client,
    get_rest,
    infer_guild,
    say,
)
from .lava import (
    TrackStoppedEvent,
    NodeData,
    RepeatMode,
    access_data,
    access_queue,
    set_data,
    get_queue,
)


async def stop(g_: IntCastable | MaybeGuildIDAware, lvc: lv.Lavalink, /) -> None:
    async with access_queue(g_, lvc) as q:
        try:
            if np_pos := q.np_time:
                q.update_paused_np_position(np_pos)
        except QueueEmptyError:
            pass
        q.is_stopped = True

    await lvc.stop(infer_guild(g_))


async def stop_in_ctxmng(
    g_: IntCastable | MaybeGuildIDAware, lvc: lv.Lavalink, data: NodeData, /
) -> None:
    g = infer_guild(g_)

    data.queue.is_stopped = True
    await set_data(g, lvc, data)
    await lvc.stop(g)


async def unstop(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> None:
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        q.is_stopped = False


async def wait_for_track_finish_event_fire():
    client = get_client()
    bot = client.get_type_dependency(hk.GatewayBot)
    assert not isinstance(bot, al.abc.Undefined)

    try:
        await bot.wait_for(TrackStoppedEvent, timeout=TIMEOUT)
    except asyncio.TimeoutError:
        return


@ctxlib.asynccontextmanager
async def while_stop(
    g_: IntCastable | MaybeGuildIDAware, lvc: lv.Lavalink, data: NodeData, /
):
    await stop_in_ctxmng(g_, lvc, data)
    await wait_for_track_finish_event_fire()
    try:
        yield
    finally:
        data.queue.is_stopped = False


async def set_pause(
    g_r_: RESTAwareType | IntCastable,
    lvc: lv.Lavalink,
    /,
    *,
    pause: Option[bool],
    respond: bool = False,
    strict: bool = False,
    update_controller: bool = False,
) -> Panic[bool]:
    g = infer_guild(g_r_)

    try:
        client = get_client(g_r_)
        emj = client.get_type_dependency(EmojiCache)
        assert not isinstance(emj, al.abc.Undefined)

        async with access_data(g, lvc) as d:
            q = d.queue
            if q.is_stopped:
                if strict:
                    raise TrackStoppedError
                return False
            if pause is None:
                pause = not q.is_paused
            if pause and q.is_paused:
                if respond:
                    assert isinstance(g_r_, RESTAwareType)
                    await err_say(g_r_, content="❗ Already paused")
                return False
            if not (pause or q.is_paused):
                if respond:
                    assert isinstance(g_r_, RESTAwareType)
                    await err_say(g_r_, content="❗ Already resumed")
                return False

            np_pos = q.np_time
            if np_pos is None:
                raise NotPlayingError

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
        if respond:
            if isinstance(g_r_, ContextishType):
                await say(g_r_, show_author=True, content=f"{e} {msg}")
            else:
                assert d.out_channel_id and not isinstance(g_r_, IntCastable)
                await say(g_r_, channel=d.out_channel_id)

        if update_controller and d.nowplaying_msg:
            if not isinstance(g_r_, RESTAwareType):
                raise RuntimeError(
                    "`g_r_` is not a `RESTAwareType` but `update_controller` was passed `True`"
                )
            rest = get_rest(g_r_)

            assert d.nowplaying_components
            edits: MapSig[ButtonBuilderType] = lambda x: x.set_emoji(
                emj[f"{msg[:-1].casefold()}_b"]
            )
            predicates: PredicateSig[ButtonBuilderType] = lambda x: x.emoji in {
                emj["pause_b"],
                emj["resume_b"],
            }

            components = edit_components(
                rest,
                *d.nowplaying_components,
                edits=edits,
                predicates=predicates,
            )

            await d.edit_now_playing_components(rest, components)
    except (QueueEmptyError, NotPlayingError):
        if strict:
            raise
        return False
    return True


async def skip(
    g_: IntCastable | ContextishType,
    lvc: lv.Lavalink,
    /,
    *,
    advance: bool = True,
    reset_repeat: bool = False,
    change_stop: bool = True,
) -> Option[lv.TrackQueue]:
    async with access_queue(g_, lvc) as q:
        skip = q.current
        if reset_repeat:
            q.reset_repeat()
        await lvc.stop(g := infer_guild(g_))
        if q.is_stopped:
            if next_t := q.next:
                await lvc.play(g, next_t.track).start()
            if advance:
                q.adv()
        if change_stop:
            q.is_stopped = False
        await set_pause(g_, lvc, pause=False)
        return skip


async def skip_abs(ctx_: ContextishType, lvc: lv.Lavalink):
    skip_t = await skip(ctx_, lvc, reset_repeat=True)

    assert skip_t is not None
    await say(ctx_, show_author=True, content=f"⏭️ ~~`{skip_t.track.info.title}`~~")


async def back(
    ctx_: ContextishType,
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


async def previous_abs(ctx_: ContextishType, lvc: lv.Lavalink):
    if (
        q := await get_queue(ctx_, lvc)
    ).repeat_mode is RepeatMode.NONE and not q.history:
        await err_say(ctx_, content="❗ This is the start of the queue")
        return

    prev = await back(ctx_, lvc)
    await say(ctx_, show_author=True, content=f"⏮️ **`{prev.track.info.title}`**")


async def seek(
    ctx: tj.abc.Context, lvc: lv.Lavalink, total_ms: int, /
) -> Fallible[int]:
    assert ctx.guild_id
    if total_ms < 0:
        raise IllegalArgumentError(Argument(total_ms, 0))
    async with access_queue(ctx, lvc) as q:
        assert q.current is not None
        if total_ms >= (song_len := q.current.track.info.length):
            raise IllegalArgumentError(Argument(total_ms, song_len))
        q.update_curr_t_started(-total_ms)
        await lvc.seek_millis(ctx.guild_id, total_ms)
        return total_ms
