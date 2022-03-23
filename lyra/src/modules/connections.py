import typing as t
import asyncio
import logging

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv


from hikari.permissions import Permissions as hkperms
from src.lib.music import music_h
from src.lib.utils import GuildConfig, get_pref, guild_c, say, err_say
from src.lib.checks import Checks, check, check_others_not_in_vc__
from src.lib.lavaimpl import get_data, access_data, access_queue
from src.lib.errors import (
    InternalError,
    NotInVoice,
    AlreadyConnected,
    Forbidden,
    RequestedToSpeak,
    ChannelMoved,
    NotConnected,
    Restricted,
)
from src.lib.consts import LOG_PAD


conns = (
    tj.Component(name='Conections', strict=True).add_check(guild_c).set_hooks(music_h)
)


logger = logging.getLogger(f"{'connections':<{LOG_PAD}}")
logger.setLevel(logging.DEBUG)


async def join(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel | hk.GuildStageChannel],
    lvc: lv.Lavalink,
    /,
) -> hk.Snowflake:
    """Joins your voice channel."""
    assert ctx.guild_id and ctx.member

    if not (ctx.cache and ctx.shards):
        raise InternalError

    if channel is None:
        # If user is connected to a voice channel
        if (
            voice_state := ctx.cache.get_voice_state(ctx.guild_id, ctx.author)
        ) is not None:
            # Join the current voice channel
            new_ch = voice_state.channel_id
        else:
            raise NotInVoice
    else:
        new_ch = channel.id
        # Join the specified voice channel

    old_conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
    assert isinstance(old_conn, dict) or old_conn is None
    assert new_ch is not None

    # Check if the bot is already connected and the user tries to change
    if old_conn:

        old_ch: t.Optional[int] = old_conn['channel_id']
        # If it's the same channel
        assert old_ch
        if old_ch == new_ch:
            raise AlreadyConnected(old_ch)

        await check_others_not_in_vc__(ctx, old_conn)
    else:
        old_ch = None

    bot_u = ctx.cache.get_me()
    assert bot_u

    bot_m = ctx.cache.get_member(ctx.guild_id, bot_u)
    assert bot_m

    my_perms = await tj.utilities.fetch_permissions(ctx.client, bot_m, channel=new_ch)
    if not (my_perms & (p := hkperms.CONNECT)):
        raise Forbidden(p, channel=new_ch)

    from src.modules.config import RESTRICTOR

    cfg = ctx.client.get_type_dependency(GuildConfig)
    assert cfg

    res_ch = cfg.get(str(ctx.guild_id), {}).get('restricted_ch', {})
    res_ch_all: list[int] = res_ch.get('all', [])
    ch_wl = res_ch.get('wl_mode', 0)

    author_perms = await tj.utilities.fetch_permissions(
        ctx.client, ctx.member, channel=ctx.channel_id
    )

    if (
        (ch_wl == 1 and new_ch not in res_ch_all)
        or (ch_wl == -1 and new_ch in res_ch_all)
    ) and not (author_perms & (hkperms.ADMINISTRATOR | RESTRICTOR)):
        raise Restricted(ch_wl, obj=new_ch)

    # Connect to the channel
    await ctx.shards.update_voice_state(ctx.guild_id, new_ch, self_deaf=True)

    # Lavasnek waits for the data on the event
    try:
        sess_conn = await lvc.wait_for_full_connection_info_insert(ctx.guild_id)
    except TimeoutError:
        raise
    # Lavasnek tells lavalink to connect
    await lvc.create_session(sess_conn)

    async with access_data(ctx, lvc) as d:
        d.out_channel_id = ctx.channel_id

    is_stage = isinstance(ctx.cache.get_guild_channel(new_ch), hk.GuildStageChannel)
    ch_type = 'stage' if is_stage else 'channel'
    if is_stage:
        await ctx.rest.edit_my_voice_state(ctx.guild_id, new_ch, request_to_speak=True)

    if old_conn and old_ch:
        logger.info(
            f"In guild {ctx.guild_id} moved   from    {old_ch} > {ch_type: <7} {new_ch}"
        )
        raise ChannelMoved(old_ch, new_ch, to_stage=is_stage)

    elif is_stage:
        logger.info(f"In guild {ctx.guild_id} joined  {ch_type: <7} {new_ch}")
        raise RequestedToSpeak(new_ch)

    logger.info(f"In guild {ctx.guild_id} joined  {ch_type: <7} {new_ch}")
    return new_ch


async def leave(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> hk.Snowflakeish:
    assert ctx.guild_id

    if not (conn := lvc.get_guild_gateway_connection_info(ctx.guild_id)):
        raise NotConnected

    assert isinstance(conn, dict)
    curr_channel: int = conn['channel_id']
    assert isinstance(curr_channel, int)

    await check_others_not_in_vc__(ctx, conn)

    async with access_data(ctx, lvc) as d:
        d.dc_on_purpose = True

    await cleanup(ctx.guild_id, ctx.client.shards, lvc)

    logger.info(f"In guild {ctx.guild_id} left    channel {curr_channel} gracefully")
    return curr_channel


async def cleanup(
    guild: hk.Snowflakeish,
    shards: t.Optional[hk.ShardAware],
    lvc: lv.Lavalink,
    /,
    *,
    also_disconns: bool = True,
) -> None:
    async with access_queue(guild, lvc) as q:
        q.clr()
    await lvc.destroy(guild)
    if shards:
        if also_disconns:
            await shards.update_voice_state(guild, None)
        await lvc.wait_for_connection_info_remove(guild)
    await lvc.remove_guild_node(guild)
    await lvc.remove_guild_from_loops(guild)


# ~


@conns.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    client: al.Injected[tj.Client],
    bot: al.Injected[hk.GatewayBot],
    lvc: al.Injected[lv.Lavalink],
):
    def _conn():
        return lvc.get_guild_gateway_connection_info(event.guild_id)

    new = event.state
    old = event.old_state

    if not await lvc.get_guild_node(event.guild_id):
        return

    bot_u = bot.get_me()
    assert bot_u

    def _in_voice() -> frozenset[hk.VoiceState]:
        conn = _conn()
        cache = client.cache
        if not conn:
            return frozenset()
        assert isinstance(conn, dict) and cache
        ch_id: int = conn['channel_id']
        return frozenset(
            filter(
                lambda v: not v.member.is_bot,
                cache.get_voice_states_view_for_channel(event.guild_id, ch_id).values(),
            )
        )

    new_vc_id = new.channel_id
    out_ch = (d := await get_data(event.guild_id, lvc)).out_channel_id
    assert out_ch

    if not d.dc_on_purpose and old and old.user_id == bot_u.id and not new.channel_id:
        await cleanup(event.guild_id, client.shards, lvc, also_disconns=False)
        await client.rest.create_message(
            out_ch,
            f"🥀📎 ~~<#{(_vc := old.channel_id)}>~~ `(Bot was forcefully disconnected)`",
        )
        logger.warning(f"In guild {event.guild_id} left    channel {_vc} forcefully")
        return

    d.dc_on_purpose = False

    if not (conn := _conn()):
        return
    assert isinstance(conn, dict)

    from .playback import set_pause

    old_is_stage = (
        None
        if not (old and old.channel_id)
        else isinstance(
            bot.cache.get_guild_channel(old.channel_id), hk.GuildStageChannel
        )
    )

    if (
        new_vc_id
        and isinstance(bot.cache.get_guild_channel(new_vc_id), hk.GuildStageChannel)
        and new.user_id == bot_u.id
    ):
        old_suppressed = getattr(old, 'is_suppressed', True)
        old_requested = getattr(old, 'requested_to_speak_at', None)

        if not old_suppressed and new.is_suppressed and old_is_stage:
            await set_pause(event, lvc, pause=True, update_controller=True)
            await client.rest.create_message(
                out_ch,
                f"👥▶️ Paused as the bot was moved to audience",
            )
        elif old_suppressed and not new.is_suppressed:
            await client.rest.create_message(
                out_ch,
                f"🎭🗣️ Became a speaker",
            )
        elif not new.requested_to_speak_at and old_requested:
            await client.rest.create_message(
                out_ch, f"❕🎭 Bot's request to speak was dismissed"
            )

    async def on_everyone_leaves_vc():
        logger.debug(
            f"In guild {event.guild_id} started channel {conn['channel_id']} inactivity timeout"
        )
        for _ in range(10):
            if len(_in_voice()) >= 1 or not (_conn()):
                logger.debug(
                    f"In guild {event.guild_id} stopped channel {conn['channel_id']} inactivity timeout"
                )
                return False
            await asyncio.sleep(60)

        __conn = _conn()
        assert isinstance(__conn, dict)

        async with access_data(event.guild_id, lvc) as d:
            d.dc_on_purpose = True
        await cleanup(event.guild_id, client.shards, lvc)
        _vc: int = __conn['channel_id']
        logger.info(
            f"In guild {event.guild_id} left    channel {_vc} due to inactivity"
        )
        await client.rest.create_message(
            out_ch, f"🍃📎 ~~<#{_vc}>~~ `(Left due to inactivity)`"
        )

        return True

    in_voice = _in_voice()
    node_vc_id: int = conn['channel_id']
    # if new.channel_id == vc and len(in_voice) == 1 and new.user_id != bot_u.id:
    #     # Someone rejoined
    #     try:
    #         await set_pause__(event.guild_id, lvc, pause=False)
    #         await client.rest.create_message(ch, f"✨⏸️ Resumed")
    #     except NotConnected:
    #         pass

    if (new_vc_id != node_vc_id) and not in_voice:
        if old and old.channel_id == node_vc_id:
            # Everyone left

            # TODO: Should be in `playback.py`
            await set_pause(event, lvc, pause=True, update_controller=True)
            await client.rest.create_message(
                out_ch, f"🕊️▶️ Paused as no one is listening"
            )

            await asyncio.wait(
                (asyncio.create_task(on_everyone_leaves_vc()),),
                return_when=asyncio.FIRST_COMPLETED,
            )


# Join


@tj.with_channel_slash_option(
    'channel',
    "Which channel? (If not given, your currently connected channel)",
    types=(hk.GuildVoiceChannel, hk.GuildStageChannel),
    default=None,
)
@tj.as_slash_command('join', "Connects the bot to a voice channel")
#
@tj.with_argument('channel', converters=tj.to_channel, default=None)
@tj.with_parser
@tj.as_message_command('join', 'j', 'connect', 'co', 'con')
#
@check(Checks.CATCH_ALL)
async def join_(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel | hk.GuildStageChannel],
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Connect the bot to a voice channel."""
    try:
        vc = await join(ctx, channel, lvc)
        await say(ctx, content=f"🖇️ <#{vc}>")
    except ChannelMoved as sig:
        txt = f"📎🖇️ ~~<#{sig.old_channel}>~~ ➜ __<#{sig.new_channel}>__"
        msg = (
            txt
            if not sig.to_stage
            else f"🎭{txt} `(Sent a request to speak. Waiting to become a speaker...)`"
        )
        await say(ctx, content=msg)
    except RequestedToSpeak as sig:
        await say(
            ctx,
            content=f"🎭📎 <#{sig.channel}> `(Sent a request to speak. Waiting to become a speaker...)`",
        )
    except NotInVoice:
        await err_say(
            ctx,
            content="❌ Please specify a voice channel or join one",
        )
    except AlreadyConnected as exc:
        await err_say(ctx, content=f"❗ Already connected to <#{exc.channel}>")
    except InternalError:
        await err_say(
            ctx,
            content="⁉️ Something internal went wrong. Please try again in few minutes",
        )
    except Forbidden as exc:
        await err_say(
            ctx,
            content=f"⛔ Not sufficient permissions to join channel <#{exc.channel}>",
        )
    except Restricted as exc:
        p = get_pref(ctx)
        await err_say(
            ctx,
            content=f"🚷 This voice channel is {'blacklisted from' if exc.mode == -1 else 'not whitelisted to'} connect{'ing' if exc.mode == -1 else ''}. Consider checking the restricted channels list from `{p}config restrict list`",
        )
    except TimeoutError:
        await err_say(
            ctx,
            content="⌛ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
        )


# Leave


@tj.as_slash_command('leave', "Leaves the voice channel and clears the queue")
#
@tj.as_message_command('leave', 'l', 'lv', 'dc', 'disconnect', 'discon')
#
@check(Checks.CATCH_ALL)
async def leave_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Stops playback of the current song."""
    assert ctx.guild_id

    try:
        vc = await leave(ctx, lvc)
    except NotConnected:
        await err_say(ctx, content="❗ Not currently connected yet")
    else:
        await say(ctx, content=f"📎 ~~<#{vc}>~~")


# -


loader = conns.load_from_scope().make_loader()
