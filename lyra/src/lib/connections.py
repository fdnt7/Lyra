import typing as t
import logging

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from hikari.permissions import Permissions as hkperms

from .utils import (
    DJ_PERMS,
    RESTRICTOR,
    ConnectionInfo,
    Contextish,
    err_say,
    fetch_permissions,
    get_client,
    get_pref,
    say,
)
from .extras import Option, Result, lgfmt
from .errors import (
    AlreadyConnected,
    ChannelMoved,
    Forbidden,
    InternalError,
    NotConnected,
    NotInVoice,
    OthersInVoice,
    RequestedToSpeak,
    Restricted,
)
from .expects import CheckErrorExpects
from .dataimpl import LyraDBCollectionType
from .lavautils import access_data, access_queue


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


# ~


async def join(
    ctx: tj.abc.Context,
    channel: Option[hk.GuildVoiceChannel | hk.GuildStageChannel],
    lvc: lv.Lavalink,
    /,
) -> Result[hk.Snowflake]:
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

        old_ch: Option[int] = old_conn['channel_id']
        # If it's the same channel
        assert old_ch
        if old_ch == new_ch:
            raise AlreadyConnected(old_ch)

        await others_not_in_vc_check_impl(ctx, old_conn)
    else:
        old_ch = None

    bot_u = ctx.cache.get_me()
    assert bot_u

    bot_m = ctx.cache.get_member(ctx.guild_id, bot_u)
    assert bot_m

    my_perms = await tj.utilities.fetch_permissions(ctx.client, bot_m, channel=new_ch)
    if not (my_perms & (p := hkperms.CONNECT)):
        raise Forbidden(p, channel=new_ch)

    cfg = ctx.client.get_type_dependency(LyraDBCollectionType)
    assert not isinstance(cfg, al.abc.Undefined)

    g_cfg = cfg.find_one({'id': str(ctx.guild_id)})
    assert g_cfg

    res_ch = g_cfg.get('restricted_ch', {})
    res_ch_all: set[int] = {
        *(
            map(
                int,
                res_ch.get('all', []),  # pyright: ignore [reportUnknownArgumentType]
            )
        )
    }
    ch_wl: t.Literal[-1, 0, 1] = res_ch.get('wl_mode', 0)

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
    sess_conn = await lvc.wait_for_full_connection_info_insert(ctx.guild_id)

    # Lavasnek tells lavalink to connect
    await lvc.create_session(sess_conn)

    async with access_data(ctx, lvc) as d:
        d.out_channel_id = ctx.channel_id

    is_stage = isinstance(ctx.cache.get_guild_channel(new_ch), hk.GuildStageChannel)
    ch_type = 'stage' if is_stage else 'channel'
    if is_stage:
        await ctx.rest.edit_my_voice_state(ctx.guild_id, new_ch, request_to_speak=True)

    if old_conn and old_ch:
        async with access_data(ctx, lvc) as d:
            d.vc_change_intended = True
        logger.info(
            f"In guild {ctx.guild_id} moved   from    {old_ch} > {ch_type: <7} {new_ch} gracefully"
        )
        raise ChannelMoved(old_ch, new_ch, to_stage=is_stage)

    elif is_stage:
        logger.info(f"In guild {ctx.guild_id} joined  {ch_type: <7} {new_ch}")
        raise RequestedToSpeak(new_ch)

    logger.info(f"In guild {ctx.guild_id} joined  {ch_type: <7} {new_ch}")
    return new_ch


async def leave(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> Result[hk.Snowflakeish]:
    assert ctx.guild_id

    if not (conn := lvc.get_guild_gateway_connection_info(ctx.guild_id)):
        raise NotConnected

    assert isinstance(conn, dict)
    curr_channel: int = conn['channel_id']
    assert isinstance(curr_channel, int)

    await others_not_in_vc_check_impl(ctx, conn)

    async with access_data(ctx, lvc) as d:
        d.vc_change_intended = True

    await cleanup(ctx.guild_id, ctx.client.shards, lvc)

    logger.info(f"In guild {ctx.guild_id} left    channel {curr_channel} gracefully")
    return curr_channel


async def cleanup(
    guild: hk.Snowflakeish,
    shards: Option[hk.ShardAware],
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


async def join_impl_precaught(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    channel: Option[hk.GuildVoiceChannel | hk.GuildStageChannel] = None,
):
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
        return sig.new_channel
    except Restricted as exc:
        p = get_pref(ctx)
        await err_say(
            ctx,
            content=f"🚷 This voice channel is {'blacklisted from being' if exc.mode == -1 else 'not whitelisted to be'} connected. Consider checking the restricted channels list from `{p}config restrict list`",
        )
    except AlreadyConnected as exc:
        await err_say(ctx, content=f"❗ Already connected to <#{exc.channel}>")
    except Forbidden as exc:
        await err_say(
            ctx,
            content=f"⛔ Not sufficient permissions to join channel <#{exc.channel}>",
        )
    except TimeoutError:
        await err_say(
            ctx,
            content="⌛ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
        )
    except InternalError:
        await CheckErrorExpects(ctx).expect_internal_error()
    else:
        return vc


async def others_not_in_vc_check_impl(
    ctx_: Contextish, conn: ConnectionInfo, /, *, perms: hkperms = DJ_PERMS
) -> Result[bool]:
    auth_perms = await fetch_permissions(ctx_)
    member = ctx_.member
    client = get_client(ctx_)
    assert client.cache and ctx_.guild_id
    channel = conn['channel_id']

    voice_states = client.cache.get_voice_states_view_for_channel(
        ctx_.guild_id, channel
    )
    others_in_voice = frozenset(
        filter(
            lambda v: member and not v.member.is_bot and v.member.id != member.id,
            voice_states.values(),
        )
    )

    if not (auth_perms & (perms | hkperms.ADMINISTRATOR)) and others_in_voice:
        raise OthersInVoice(channel)
    return True
