import typing as t
import logging

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from .extras import Option, Fallible, lgfmt
from .dataimpl import LyraDBCollectionType

from .utils import (
    DJ_PERMS,
    RESTRICTOR,
    ConnectionInfo,
    ContextishType,
    err_say,
    fetch_permissions,
    get_client,
    say,
)
from .cmd import CommandIdentifier, get_full_cmd_repr_from_identifier
from .lava import ConnectionCommandsInvokedEvent, NodeDataRef, access_data


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


# ~


async def join(
    ctx: tj.abc.Context,
    channel: Option[hk.GuildVoiceChannel | hk.GuildStageChannel],
    lvc: lv.Lavalink,
    /,
) -> Fallible[hk.Snowflake]:
    """Joins your voice channel."""
    from .errors import (
        AlreadyConnectedError,
        ChannelMoved,
        ForbiddenError,
        InternalError,
        NotInVoiceError,
        RequestedToSpeak,
        RestrictedError,
    )

    assert ctx.guild_id and ctx.member

    if not (ctx.cache and ctx.shards):
        raise InternalError

    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    cfg = ctx.client.get_type_dependency(LyraDBCollectionType)
    ndt = ctx.client.get_type_dependency(NodeDataRef)
    assert (
        not isinstance(bot, al.abc.Undefined)
        and not isinstance(cfg, al.abc.Undefined)
        and not isinstance(ndt, al.abc.Undefined)
    )

    if channel is None:
        # If user is connected to a voice channel
        if (
            voice_state := ctx.cache.get_voice_state(ctx.guild_id, ctx.author)
        ) is not None:
            # Join the current voice channel
            new_ch = voice_state.channel_id
        else:
            raise NotInVoiceError
    else:
        new_ch = channel.id
        # Join the specified voice channel

    old_conn = t.cast(
        Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx.guild_id)
    )
    assert new_ch is not None

    # Check if the bot is already connected and the user tries to change
    if old_conn:

        old_ch: Option[int] = old_conn['channel_id']
        # If it's the same channel
        assert old_ch
        if old_ch == new_ch:
            raise AlreadyConnectedError(old_ch)

        await others_not_in_vc_check_impl(ctx, old_conn)
    else:
        old_ch = None

    g = ctx.get_guild()
    assert g

    bot_m = g.get_my_member()
    assert bot_m

    my_perms = await tj.permissions.fetch_permissions(ctx.client, bot_m, channel=new_ch)
    if not (my_perms & (p := hk.Permissions.CONNECT)):
        raise ForbiddenError(p, channel=new_ch)

    g_cfg = cfg.find_one({'id': str(ctx.guild_id)})
    assert g_cfg

    res_ch = g_cfg.get('restricted_ch', {})
    res_ch_all: set[int] = {
        *(
            map(
                int,
                res_ch.get('all', t.cast(list[int], [])),
            )
        )
    }
    ch_wl: t.Literal[-1, 0, 1] = res_ch.get('wl_mode', 0)

    author_perms = await tj.permissions.fetch_permissions(
        ctx.client, ctx.member, channel=ctx.channel_id
    )

    if (
        (ch_wl == 1 and new_ch not in res_ch_all)
        or (ch_wl == -1 and new_ch in res_ch_all)
    ) and not (author_perms & (hk.Permissions.ADMINISTRATOR | RESTRICTOR)):
        raise RestrictedError(ch_wl, obj=new_ch)

    # Connect to the channel
    await ctx.shards.update_voice_state(ctx.guild_id, new_ch, self_deaf=True)

    # Lavasnek waits for the data on the event
    sess_conn = await lvc.wait_for_full_connection_info_insert(ctx.guild_id)

    # Lavasnek tells lavalink to connect
    await lvc.create_session(sess_conn)

    async with access_data(ctx, lvc) as d:
        ndt.setdefault(ctx.guild_id, d)
        d.out_channel_id = ctx.channel_id

    is_stage = isinstance(ctx.cache.get_guild_channel(new_ch), hk.GuildStageChannel)
    ch_type = 'stage' if is_stage else 'channel'
    if is_stage:
        await ctx.rest.edit_my_voice_state(ctx.guild_id, new_ch, request_to_speak=True)

    if old_conn and old_ch:
        bot.dispatch(ConnectionCommandsInvokedEvent(bot))
        logger.info(
            f"In guild {ctx.guild_id} moved   from    {old_ch} > {ch_type: <7} {new_ch} gracefully"
        )
        raise ChannelMoved(old_ch, new_ch, to_stage=is_stage)

    elif is_stage:
        logger.info(f"In guild {ctx.guild_id} joined  {ch_type: <7} {new_ch}")
        raise RequestedToSpeak(new_ch)

    logger.info(f"In guild {ctx.guild_id} joined  {ch_type: <7} {new_ch}")
    return new_ch


async def leave(ctx: tj.abc.Context, lvc: lv.Lavalink, /) -> Fallible[hk.Snowflakeish]:
    from .errors import NotConnectedError

    assert ctx.guild_id

    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    ndt = ctx.client.get_type_dependency(NodeDataRef)
    assert not isinstance(bot, al.abc.Undefined) and not isinstance(
        ndt, al.abc.Undefined
    )

    if not (
        conn := t.cast(
            ConnectionInfo, lvc.get_guild_gateway_connection_info(ctx.guild_id)
        )
    ):
        raise NotConnectedError

    curr_channel: int = t.cast(int, conn['channel_id'])

    await others_not_in_vc_check_impl(ctx, conn)

    await cleanup(ctx.guild_id, ndt, lvc, bot=bot, also_del_np_msg=False)

    bot.dispatch(ConnectionCommandsInvokedEvent(bot))
    logger.info(f"In guild {ctx.guild_id} left    channel {curr_channel} gracefully")
    return curr_channel


@t.overload
async def cleanup(
    guild: hk.Snowflakeish,
    ndt: NodeDataRef,
    lvc: lv.Lavalink,
    /,
    bot: hk.GatewayBot = ...,
    *,
    also_disconn: t.Literal[True] = True,
    also_del_np_msg: t.Literal[False] = False,
) -> None:
    ...


@t.overload
async def cleanup(
    guild: hk.Snowflakeish,
    ndt: NodeDataRef,
    lvc: lv.Lavalink,
    /,
    bot: hk.GatewayBot = ...,
    *,
    also_disconn: t.Literal[False] = False,
    also_del_np_msg: t.Literal[True] = True,
) -> None:
    ...


@t.overload
async def cleanup(
    guild: hk.Snowflakeish,
    ndt: NodeDataRef,
    lvc: lv.Lavalink,
    /,
    bot: Option[hk.GatewayBot] = None,
    *,
    also_disconn: t.Literal[False] = False,
    also_del_np_msg: t.Literal[False] = False,
) -> None:
    ...


async def cleanup(
    guild: hk.Snowflakeish,
    ndt: NodeDataRef,
    lvc: lv.Lavalink,
    /,
    bot: Option[hk.GatewayBot] = None,
    *,
    also_disconn: bool = True,
    also_del_np_msg: bool = True,
) -> None:
    await lvc.destroy(guild)
    if also_disconn:
        assert bot
        await bot.update_voice_state(guild, None)
    if also_del_np_msg:
        assert bot
        d = ndt[guild]
        if d.out_channel_id and d.nowplaying_msg:
            await bot.rest.delete_messages(d.out_channel_id, d.nowplaying_msg)
    await lvc.wait_for_connection_info_remove(guild)
    ndt.pop(guild)
    await lvc.remove_guild_node(guild)
    await lvc.remove_guild_from_loops(guild)


async def join_impl_precaught(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    channel: Option[hk.GuildVoiceChannel | hk.GuildStageChannel] = None,
):
    from .errors import (
        AlreadyConnectedError,
        ChannelMoved,
        ForbiddenError,
        InternalError,
        RestrictedError,
        CheckErrorExpects,
    )

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
    except RestrictedError as exc:
        cmd_r = get_full_cmd_repr_from_identifier(
            CommandIdentifier.CONFIG_RESTRICT_LIST, ctx
        )
        await err_say(
            ctx,
            content=f"🚷 This voice channel is {'blacklisted from being' if exc.mode == -1 else 'not whitelisted to be'} connected. Consider checking the restricted channels list from {cmd_r}",
        )
    except AlreadyConnectedError as exc:
        await err_say(ctx, content=f"❗ Already connected to <#{exc.channel}>")
    except ForbiddenError as exc:
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
    ctx_: ContextishType, conn: ConnectionInfo, /, *, perms: hk.Permissions = DJ_PERMS
) -> Fallible[bool]:
    from .errors import OthersInVoiceError

    auth_perms = await fetch_permissions(ctx_)
    member = ctx_.member
    client = get_client(ctx_)
    assert client.cache and ctx_.guild_id and member
    channel = conn['channel_id']

    voice_states = client.cache.get_voice_states_view_for_channel(
        ctx_.guild_id, channel
    )
    others_in_voice = frozenset(
        filter(
            lambda v: not v.member.is_bot and v.member.id != member.id,
            voice_states.values(),
        )
    )

    if not (auth_perms & (perms | hk.Permissions.ADMINISTRATOR)) and others_in_voice:
        raise OthersInVoiceError(channel)
    return True
