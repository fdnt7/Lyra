import typing as t

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from .utils import (
    Q_CHUNK,
    TIMEOUT,
    guild_c,
    disable_components,
    err_say,
    get_cmd_repr,
    get_pref,
    say,
)
from .extras import Result, chunk, chunk_b, to_stamp, wr
from .expects import CheckErrorExpects
from .errors import (
    NotConnected,
    VotingTimeout,
)
from .lavautils import RepeatMode, access_data, get_queue


music_h = tj.AnyHooks()


@music_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    expect = CheckErrorExpects(ctx)
    return await expect.expect(error)


def init_component(
    dunder_name: str,
    /,
    *,
    guild_check: bool = True,
    music_hook: bool = True,
    other_checks: t.Iterable[tj.abc.CheckSig] = (),
    other_hooks: t.Iterable[tj.abc.Hooks[tj.abc.Context]] = (),
):
    comp = tj.Component(name=dunder_name.split('.')[-1].capitalize(), strict=True)
    if guild_check:
        comp.add_check(guild_c)
    if music_hook:
        comp.set_hooks(music_h)
    *(comp.add_check(c) for c in other_checks),
    *(comp.set_hooks(h) for h in other_hooks),

    return comp


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


async def init_listeners_voting(
    ctx: tj.abc.Context, lvc: lv.Lavalink, /
) -> Result[None]:
    assert ctx.member and ctx.guild_id and ctx.client.cache

    cmd_n = ''.join((get_pref(ctx), '~ ', get_cmd_repr(ctx)))
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
    listeners = (
        *filter(
            lambda v: not v.member.is_bot,
            voice_states.values(),
        ),
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

    msg = await say(
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
                    await err_say(inter, content="❗ You've already voted")
                    continue

                voted.add(user_id)

                await inter.create_initial_response(
                    hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
                )
                await inter.edit_initial_response(embed=v_embed())

            if len(voted) >= threshold:
                await inter.edit_initial_response(
                    components=(*disable_components(inter.app.rest, row),)
                )
                return

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, row),)
        )
        raise VotingTimeout


async def generate_queue_embeds(
    ctx: tj.abc.Context, lvc: lv.Lavalink, /
) -> tuple[hk.Embed, ...]:
    assert not ((ctx.guild_id is None) or (ctx.cache is None))
    q = await get_queue(ctx, lvc)
    if np := q.current:
        np_info = np.track.info
        req = ctx.cache.get_member(ctx.guild_id, np.requester)
        assert req is not None
        np_text = f"```arm\n{q.pos+1: >2}. {to_stamp(np_info.length):>6} | {wr(np_info.title, 50)} |\n````Requested by:` {req.mention}"
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

    _base_embed = hk.Embed(title="💿 Queue", description=desc, color=color,).set_footer(
        f"Queue Duration: {to_stamp(queue_elapsed)} / {to_stamp(queue_durr)} ({to_stamp(queue_eta)} Left)"
    )

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
                f"{q.pos: >2}․ {to_stamp(prev.track.info.length):>6} # {wr(prev.track.info.title, 51)}"
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
                    f"{j: >2}․ {to_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 51)}"
                    for j, t_ in enumerate(upcoming[:Q_CHUNK], q.pos + 2)
                )
                or _empty,
            ),
        )
    )

    prev_embeds = (
        copy.deepcopy(_base_embed).add_field(
            "Previous",
            _format_prev
            % "\n".join(
                f"{j: >2}․ {to_stamp(t_.track.info.length):>6} # {wr(t_.track.info.title, 51)}"
                for j, t_ in enumerate(
                    prev_slice,
                    1
                    + max(0, i) * Q_CHUNK
                    + (0 if i == -1 else len(his[:-1]) % Q_CHUNK),
                )
            ),
        )
        for i, prev_slice in enumerate(chunk_b(his[:-1], Q_CHUNK), -1)
        if prev_slice
    )

    next_embeds = (
        copy.deepcopy(_base_embed).add_field(
            "Next up",
            _format
            % "\n".join(
                f"{j: >2}․ {to_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 51)}"
                for j, t_ in enumerate(next_slice, q.pos + 2 + i * Q_CHUNK)
            ),
        )
        for i, next_slice in enumerate(chunk(upcoming[Q_CHUNK:], Q_CHUNK), 1)
        if next_slice
    )

    return (*prev_embeds, np_embed, *next_embeds)
