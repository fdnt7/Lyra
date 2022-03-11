import typing as t
import asyncio
import logging
import datetime as dt

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from .utils import (
    Q_DIV,
    get_pref,
    get_cmd_n,
    reply,
    err_reply,
    delete_after,
    disable_components,
)
from .errors import NotConnected, NotInVoice, Forbidden, RequestedToSpeak, VotingTimeout
from .extras import VoidCoroutine, NULL, TIMEOUT, ms_stamp, wr, chunk, chunk_b
from .lavaimpl import (
    get_queue,
    access_data,
    RepeatMode,
)

from src.modules.connections import join__, leave__, cleanups__
from src.modules.playback import skip__


STOP_REFRESH = 0.15

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


_P = t.ParamSpec('_P')


def auto_connect_vc(func: t.Callable[_P, VoidCoroutine]):
    async def inner(*args: _P.args, **kwargs: _P.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.Context)), NULL)
        lvc = next((a for a in kwargs.values() if isinstance(a, lv.Lavalink)), NULL)

        assert ctx and lvc
        p = get_pref(ctx)

        assert ctx.guild_id
        conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)

        async def __join():
            assert ctx
            if not conn:
                # Join the users voice channel if we are not already connected
                try:
                    await join__(ctx, None, lvc)
                except NotInVoice:
                    await err_reply(
                        ctx,
                        content=f"❌ Please join a voice channel first. You can also do `{p}join channel:` `[🔊 ...]`",
                    )
                    return
                except TimeoutError:
                    await err_reply(
                        ctx,
                        content="⌛ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
                    )
                    return
                except Forbidden as exc:
                    await err_reply(
                        ctx,
                        content=f"⛔ Not sufficient permissions to join channel <#{exc.channel}",
                    )
                    return
                except RequestedToSpeak as sig:
                    bot = ctx.client.get_type_dependency(hk.GatewayBot)
                    assert bot

                    if isinstance(ctx, tj.abc.AppCommandContext):
                        await ctx.defer()

                    wait_msg = await ctx.client.rest.create_message(
                        ctx.channel_id,
                        f"⏳🎭📎 <#{sig.channel}> `(Sent a request to speak. Waiting to become a speaker...)`",
                    )

                    bot_u = bot.get_me()
                    assert bot_u

                    try:
                        await bot.wait_for(
                            hk.VoiceStateUpdateEvent,
                            timeout=TIMEOUT // 2,
                            predicate=lambda e: e.state.user_id == bot_u.id
                            and bool(e.state.channel_id)
                            and not e.state.is_suppressed
                            and bool(ctx.client.cache)
                            and isinstance(
                                ctx.client.cache.get_guild_channel(sig.channel),
                                hk.GuildStageChannel,
                            ),
                        )
                    except asyncio.TimeoutError:
                        await wait_msg.edit(
                            "⌛ Waiting timed out. Invite the bot to speak and invoke the command again",
                        )
                        asyncio.create_task(delete_after(ctx, wait_msg, time=5.0))
                        return
            return True

        ch = ctx.get_channel()
        assert ch is not None
        if isinstance(ctx, tj.abc.MessageContext):
            async with ch.trigger_typing():
                if not await __join():
                    return
        else:
            if not await __join():
                return

        await func(*args, **kwargs)

    return inner


async def init_listeners_voting(ctx: tj.abc.Context, lvc: lv.Lavalink, /):
    assert ctx.member and ctx.guild_id and ctx.client.cache

    cmd_n = ''.join((get_pref(ctx), get_cmd_n(ctx)))
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert bot

    row = (
        ctx.rest.build_action_row()
        .add_button(hk.ButtonStyle.SUCCESS, 'vote')
        .set_emoji('🗳️')
        .add_to_container()
    )

    conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
    assert isinstance(conn, dict)

    channel: int = conn['channel_id']
    voice_states = ctx.client.cache.get_voice_states_view_for_channel(
        ctx.guild_id, channel
    )
    listeners = tuple(
        filter(
            lambda v: not v.member.is_bot,
            voice_states.values(),
        )
    )

    voted = {ctx.author.id}
    threshold = round((len(listeners) + 1) / 2)

    pad_f: t.Callable[[int], int] = lambda x: int(38 * x / 31 + 861 / 31)

    m = ctx.member

    def v_embed():
        assert ctx.member
        vote_n = len(voted)
        vote_b = ('─' * (pad_n := pad_f(len(ctx.member.display_name)))).replace(
            '─', '▬', pad_n * vote_n // threshold
        )
        return hk.Embed(
            title=f"🎫 Voting for command `{cmd_n}`",
            description=f"{m.mention} wanted to use the command `{cmd_n}`\n\n`{vote_b}` **{vote_n}/{threshold}**{' 🎉' if vote_n==threshold else ''}",
            color=0xC2CED5,
        ).set_footer("Press the green button below to cast a vote!")

    msg = await reply(
        ctx,
        ensure_result=True,
        embed=v_embed(),
        components=(row,),
    )

    np = (await get_queue(ctx, lvc)).current
    np_timeout = TIMEOUT if not np else np.track.info.length // 1_000

    with bot.stream(hk.InteractionCreateEvent, timeout=min(TIMEOUT, np_timeout)).filter(
        lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.message == msg
        and e.interaction.user.id in {u.user_id for u in listeners}
    ) as stream:

        async for event in stream:
            inter = event.interaction
            assert isinstance(inter, hk.ComponentInteraction)

            key = inter.custom_id
            if key == 'vote':
                if (user_id := inter.user.id) in voted:
                    await err_reply(inter, content="❗ You've already voted")
                    continue

                voted.add(user_id)

                await inter.create_initial_response(
                    hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
                )
                await inter.edit_initial_response(embed=v_embed())

            if len(voted) >= threshold:
                await reply(inter, content='☑️ Vote threshold reached')
                await inter.edit_initial_response(
                    components=(*disable_components(inter.app.rest, row),)
                )
                return

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, row),)
        )
        raise VotingTimeout


async def generate_nowplaying_embed__(
    guild_id: hk.Snowflakeish, cache: hk.api.Cache, lvc: lv.Lavalink, /
):
    q = await get_queue(guild_id, lvc)
    # e = '⏹️' if q.is_stopped else ('▶️' if q.is_paused else '⏸️')

    curr_t = q.current
    assert curr_t

    t_info = curr_t.track.info
    req = cache.get_member(guild_id, curr_t.requester)
    assert req, "That member has left the guild"

    song_len = ms_stamp(t_info.length)
    # np_pos = q.np_position // 1_000
    # now = int(time.time())

    embed = (
        hk.Embed(
            title=f"🎧 {t_info.title}",
            description=f'📀 **{t_info.author}** ({song_len})',
            url=t_info.uri,
            color=q.curr_t_palette[0],
            timestamp=dt.datetime.now().astimezone(),
        )
        .set_author(name="Currently playing")
        .set_footer(
            f"Requested by: {req.display_name}",
            icon=req.avatar_url or req.default_avatar_url,
        )
        .set_thumbnail(q.curr_t_thumbnail)
    )
    return embed


music_h = tj.AnyHooks()


@music_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    if t := isinstance(error, lv.NetworkError):
        await ctx.respond("⁉️ A network error has occurred")
        return t
    return t


@music_h.with_post_execution
async def post_execution(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    assert ctx.guild_id

    try:
        async with access_data(ctx, lvc) as d:
            d.out_channel_id = ctx.channel_id
    except NotConnected:
        pass


## Info


async def generate_queue_embeds__(
    ctx: tj.abc.Context, lvc: lv.Lavalink, /
) -> tuple[hk.Embed]:
    assert not ((ctx.guild_id is None) or (ctx.cache is None))
    q = await get_queue(ctx, lvc)
    if np := q.current:
        np_info = np.track.info
        req = ctx.cache.get_member(ctx.guild_id, np.requester)
        assert req is not None
        np_text = f"```arm\n{q.pos+1: >2}. {ms_stamp(np_info.length):>6} | {wr(np_info.title, 50)} |\n````Requested by:` {req.mention}"
    else:
        np_text = f"```yaml\n{'---':^63}\n```"

    queue_durr = sum(t.track.info.length for t in q)
    queue_elapsed = sum(t.track.info.length for t in q.history) + (q.np_position or 0)
    queue_eta = queue_durr - queue_elapsed

    q = await get_queue(ctx, lvc)
    prev = None if not (his := q.history) else his[-1]
    upcoming = q.upcoming

    desc = (
        ""
        if q.repeat_mode is RepeatMode.NONE
        else (
            "**```diff\n+| Repeating this entire queue\n```**"
            if q.repeat_mode is RepeatMode.ALL
            else "**```diff\n-| Repeating the current track\n```**"
        )
    )

    color = None if q.is_paused or not q.current else q.curr_t_palette[2]

    _base_embed = hk.Embed(
        title="💿 Queue",
        description=desc,
        color=color,
    ).set_footer(f"Queue Duration: {ms_stamp(queue_elapsed)} / {ms_stamp(queue_durr)}")

    _format = f"```{'brainfuck' if q.repeat_mode is RepeatMode.ONE else 'css'}\n%s\n```"
    _format_prev = (
        f"```{'brainfuck' if q.repeat_mode is RepeatMode.ONE else 'yaml'}\n%s\n```"
    )
    _empty = f"{'---':^63}"

    import copy

    np_embed = (
        copy.deepcopy(_base_embed)
        .add_field(
            "Previous",
            _format_prev
            % (
                f"{q.pos: >2}․ {ms_stamp(prev.track.info.length):>6} # {wr(prev.track.info.title, 51)}"
                if prev
                else _empty
            ),
        )
        .add_field(
            f"{'🎶 ' if np and not q.is_paused else ''}Now playing",
            np_text,
        )
        .add_field(
            "Next up",
            _format
            % (
                "\n".join(
                    f"{j: >2}․ {ms_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 51)}"
                    for j, t_ in enumerate(upcoming[:Q_DIV], q.pos + 2)
                )
                or _empty,
            ),
        )
    )

    prev_embeds = [
        copy.deepcopy(_base_embed).add_field(
            "Previous",
            _format_prev
            % "\n".join(
                f"{j: >2}․ {ms_stamp(t_.track.info.length):>6} # {wr(t_.track.info.title, 51)}"
                for j, t_ in enumerate(
                    prev_slice,
                    1 + max(0, i) * Q_DIV + (0 if i == -1 else len(his[:-1]) % Q_DIV),
                )
            ),
        )
        for i, prev_slice in enumerate(chunk_b(his[:-1], Q_DIV), -1)
        if prev_slice
    ]

    next_embeds = [
        copy.deepcopy(_base_embed).add_field(
            "Next up",
            _format
            % "\n".join(
                f"{j: >2}․ {ms_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 51)}"
                for j, t_ in enumerate(next_slice, q.pos + 2 + i * Q_DIV)
            ),
        )
        for i, next_slice in enumerate(chunk(upcoming[Q_DIV:], Q_DIV), 1)
        if next_slice
    ]

    return tuple(prev_embeds + [np_embed] + next_embeds)
