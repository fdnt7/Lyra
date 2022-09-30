import typing as t
import itertools as it

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from .consts import Q_CHUNK, TIMEOUT
from .extras import (
    Fallible,
    Option,
    MapSig,
    IterableOr,
    chunk,
    chunk_b,
    map_in_place,
    to_stamp,
    wr,
)
from .errors import (
    NotConnectedError,
    VotingTimeoutError,
    CheckErrorExpects,
)
from .utils import (
    Style,
    Fore,
    ConnectionInfo,
    ANSI_BLOCK,
    guild_c,
    disable_components,
    err_say,
    say,
    cl,
)
from .cmd import get_full_cmd_repr
from .lava import RepeatMode, access_data, get_queue


music_h = tj.AnyHooks()


@music_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    expect = CheckErrorExpects(ctx)
    return await expect.expect(error)


def __init_component__(
    dunder_name: str,
    /,
    *,
    guild_check: bool = True,
    music_hook: bool = True,
    other_checks: IterableOr[tj.abc.CheckSig] = (),
    other_hooks: IterableOr[tj.abc.Hooks[tj.abc.Context]] = (),
):
    comp = tj.Component(name=dunder_name.split('.')[-1].capitalize(), strict=True)
    if guild_check:
        comp.add_check(guild_c)
    if music_hook:
        comp.set_hooks(music_h)

    other_hooks = (
        (other_hooks,) if isinstance(other_hooks, tj.abc.Hooks) else other_hooks
    )
    other_checks = (
        other_checks if isinstance(other_checks, t.Iterable) else (other_checks,)
    )
    map_in_place(lambda c: comp.add_check(c), other_checks)
    map_in_place(lambda h: comp.set_hooks(h), other_hooks)

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
    except NotConnectedError:
        pass


async def start_listeners_voting(
    ctx: tj.abc.Context, lvc: lv.Lavalink, /
) -> Fallible[None]:
    assert ctx.member and ctx.guild_id and ctx.client.cache

    cmd_r = get_full_cmd_repr(ctx)
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert not isinstance(bot, al.abc.Undefined)

    row = (
        ctx.rest.build_action_row()
        .add_button(hk.ButtonStyle.SUCCESS, 'vote')
        .set_emoji('🗳️')
        .add_to_container()
    )

    conn = t.cast(
        Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx.guild_id)
    )
    assert conn is not None

    channel: int = conn['channel_id']
    voice_states = ctx.client.cache.get_voice_states_view_for_channel(
        ctx.guild_id, channel
    )
    listeners = frozenset(
        filter(
            lambda v: not v.member.is_bot,
            voice_states.values(),
        )
    )

    voted = {ctx.author.id}
    threshold = round((len(listeners) + 1) / 2)

    pad_f: MapSig[int] = lambda x: int(38 * x / 31 + 861 / 31)

    m = ctx.member

    def v_embed():
        assert ctx.member
        vote_n = len(voted)
        vote_b = ('─' * (pad_n := pad_f(len(ctx.member.display_name)))).replace(
            '─', '▬', pad_n * vote_n // threshold
        )
        return hk.Embed(
            title=f"🎫 Voting for command {cmd_r}",
            description=f"{m.mention} wanted to use the command {cmd_r}\n\n`{vote_b}` **{vote_n}/{threshold}**{' 🎉' if vote_n==threshold else ''}",
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
            inter = t.cast(hk.ComponentInteraction, event.interaction)

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
        raise VotingTimeoutError


async def generate_queue_embeds(
    ctx: tj.abc.Context, lvc: lv.Lavalink, /
) -> it.chain[hk.Embed]:
    assert not ((ctx.guild_id is None) or (ctx.cache is None))
    q = await get_queue(ctx, lvc)
    _empty = cl(f"{'---':^63}", fore=Fore.D)

    if np := q.current:
        np_info = np.track.info
        req = ctx.cache.get_member(ctx.guild_id, np.requester)
        assert req is not None
        np_text = ''.join(
            (
                ANSI_BLOCK
                % "{} {} {} {}".format(
                    cl(f"{q.pos+1: >2}.", fore=Fore.M),
                    cl(f"{to_stamp(np_info.length):>6}", fore=Fore.W),
                    cl('|', fore=Fore.D),
                    cl(f"{wr(np_info.title, 50)}", style=Style.B, fore=Fore.M),
                ),
                f"📨 {req.mention}",
            )
        )
    else:
        np_text = ANSI_BLOCK % _empty

    queue_durr = q.total_durr
    queue_elapsed = sum(t.track.info.length for t in q.history) + (q.np_time or 0)
    queue_eta = queue_durr - queue_elapsed

    q = await get_queue(ctx, lvc)
    prev = None if not (his := q.history) else his[-1]
    upcoming = q.upcoming

    desc = (
        ""
        if q.repeat_mode is RepeatMode.NONE
        else ANSI_BLOCK
        % (
            "{} {} {}".format(
                cl('⮎⮌', style=Style.B, fore=Fore.G),
                cl('•', fore=Fore.D),
                cl("Repeating this entire queue", fore=Fore.G),
            )
            if q.repeat_mode is RepeatMode.ALL
            else "{} {} {}".format(
                cl('⮎₁⮌', style=Style.B, fore=Fore.C),
                cl('•', fore=Fore.D),
                cl("Repeating the current track", fore=Fore.C),
            )
        )
    )

    color = q.curr_t_palette[2] if q.is_playing else None

    _base_embed = hk.Embed(title="≡♪ Queue", description=desc, color=color,).set_footer(
        f"⌛ {to_stamp(queue_elapsed)} (-{to_stamp(queue_eta)}) / {to_stamp(queue_durr)}ㅤ•ㅤ{q.sane_pos+1} (-{len(q)-q.sane_pos-1}) / {len(q)}"
    )

    import copy

    np_embed = (
        copy.deepcopy(_base_embed)
        .add_field(
            "Previous",
            ANSI_BLOCK
            % (
                "{} {}".format(
                    cl(f"{q.pos: >2}.", fore=Fore.W),
                    cl(
                        f"{to_stamp(prev.track.info.length):>6} | {wr(prev.track.info.title, 50)}",
                        fore=Fore.D,
                    ),
                )
                if prev
                else _empty
            ),
        )
        .add_field(
            f"{'🎶 ' if q.is_playing else ''}Now playing",
            np_text,
        )
        .add_field(
            "Next up",
            ANSI_BLOCK
            % (
                "\n".join(
                    "{} {} {} {}".format(
                        cl(f"{j: >2}.", fore=Fore.B),
                        cl(f"{to_stamp(t_.track.info.length):>6}"),
                        cl('|', fore=Fore.D),
                        cl(f"{wr(t_.track.info.title, 50)}", fore=Fore.B),
                    )
                    for j, t_ in enumerate(upcoming[:Q_CHUNK], q.pos + 2)
                )
                or _empty,
            ),
        )
    )

    prev_embeds = (
        copy.deepcopy(_base_embed).add_field(
            "Previous",
            ANSI_BLOCK
            % "\n".join(
                "{} {}".format(
                    cl(f"{j: >2}.", fore=Fore.W),
                    cl(
                        f"{to_stamp(t_.track.info.length):>6} | {wr(t_.track.info.title, 50)}",
                        fore=Fore.D,
                    ),
                )
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
            ANSI_BLOCK
            % "\n".join(
                "{} {} {} {}".format(
                    cl(f"{j: >2}.", fore=Fore.B),
                    cl(f"{to_stamp(t_.track.info.length):>6}"),
                    cl('|', fore=Fore.D),
                    cl(f"{wr(t_.track.info.title, 50)}", fore=Fore.B),
                )
                for j, t_ in enumerate(next_slice, q.pos + 2 + i * Q_CHUNK)
            ),
        )
        for i, next_slice in enumerate(chunk(upcoming[Q_CHUNK:], Q_CHUNK), 1)
        if next_slice
    )

    return it.chain(prev_embeds, (np_embed,), next_embeds)
