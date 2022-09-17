import typing as t
import asyncio

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from ..lib.connections import logger, cleanup, join_impl_precaught, leave
from ..lib.cmd.ids import CommandIdentifier as C
from ..lib.cmd.compose import with_identifier
from ..lib.extras import Option, Panic
from ..lib.utils import ConnectionInfo, JoinableChannelType, dj_perms_fmt, say, err_say
from ..lib.lava.utils import get_data
from ..lib.lava.events import ConnectionCommandsInvokedEvent
from ..lib.musicutils import __init_component__
from ..lib.errors import (
    NotInVoice,
    OthersInVoice,
    RequestedToSpeak,
    NotConnected,
)


conns = __init_component__(__name__)


# ~


async def to_voice_or_stage_channels(
    value: str, /, ctx: al.Injected[tj.abc.Context]
) -> Panic[JoinableChannelType]:
    ch = await tj.to_channel(value, ctx)
    if not isinstance(ch, JoinableChannelType):
        raise tj.ConversionError(
            "The given channel is a not a voice nor a stage channel", value
        )
    return ch


@conns.with_listener()
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    client: al.Injected[tj.Client],
    bot: al.Injected[hk.GatewayBot],
    lvc: al.Injected[lv.Lavalink],
):
    def conn():
        return t.cast(
            Option[ConnectionInfo],
            lvc.get_guild_gateway_connection_info(event.guild_id),
        )

    new = event.state
    old = event.old_state

    if not await lvc.get_guild_node(event.guild_id):
        return

    bot_u = bot.get_me()
    assert bot_u

    async def users_in_vc() -> t.Collection[hk.VoiceState]:
        _conn = conn()
        cache = client.cache
        if not _conn:
            return frozenset()
        assert cache
        ch_id: int = _conn['channel_id']
        return (
            await cache.get_voice_states_view_for_channel(event.guild_id, ch_id)
            .iterator()
            .filter(lambda v: not v.member.is_bot)
            .collect(frozenset)
        )

    new_vc_id = new.channel_id
    out_ch = (await get_data(event.guild_id, lvc)).out_channel_id
    assert out_ch

    try:
        conn_cmd_invoked = await bot.wait_for(
            ConnectionCommandsInvokedEvent, timeout=0.5
        )
    except asyncio.TimeoutError:
        conn_cmd_invoked = None

    # print(conn_cmd_invoked)
    if not conn_cmd_invoked and old and old.user_id == bot_u.id:
        if not new.channel_id:
            await cleanup(event.guild_id, client.shards, lvc, also_disconns=False)
            await bot.rest.create_message(
                out_ch,
                f"🥀📎 ~~<#{(_vc := old.channel_id)}>~~ `(Bot was forcefully disconnected)`",
            )
            logger.warning(
                f"In guild {event.guild_id} left    channel {_vc} forcefully"
            )
            return
        is_stage = isinstance(
            bot.cache.get_guild_channel(new.channel_id), hk.GuildStageChannel
        )
        ch_type = 'stage' if is_stage else 'channel'
        await bot.rest.create_message(
            out_ch,
            f"🥀📎🖇️ ~~<#{old.channel_id}>~~ ➜ __<#{new_vc_id}>__ `(Bot was forcefully moved)`",
        )
        logger.warning(
            f"In guild {event.guild_id} moved   from    {old.channel_id} > {ch_type: <7} {new_vc_id} forcefully"
        )
        return

    if not (_conn := conn()):
        return

    async def on_everyone_leaves_vc():
        logger.debug(
            f"In guild {event.guild_id} started channel {_conn['channel_id']} inactivity timeout"
        )
        for _ in range(10):
            if len(await users_in_vc()) >= 1 or not conn():
                logger.debug(
                    f"In guild {event.guild_id} stopped channel {_conn['channel_id']} inactivity timeout"
                )
                return False
            await asyncio.sleep(60)

        __conn = conn()
        assert __conn

        await cleanup(event.guild_id, client.shards, lvc)
        _vc: int = __conn['channel_id']
        logger.info(
            f"In guild {event.guild_id} left    channel {_vc} due to inactivity"
        )
        await client.rest.create_message(
            out_ch, f"🍃📎 ~~<#{_vc}>~~ `(Left due to inactivity)`"
        )

        return True

    in_voice = await users_in_vc()
    node_vc_id: int = _conn['channel_id']

    if (
        new_vc_id != node_vc_id
        and not in_voice
        and old
        and old.channel_id == node_vc_id
    ):
        # Everyone left
        await asyncio.wait(
            (asyncio.create_task(on_everyone_leaves_vc()),),
            return_when=asyncio.FIRST_COMPLETED,
        )


# /join


# TODO: Use annotation-based option declaration once declaring positional-only argument is possible
@with_identifier(C.JOIN)
# -
@tj.with_channel_slash_option(
    'channel',
    "Which channel? (If not given, your currently connected channel)",
    types=(hk.GuildVoiceChannel, hk.GuildStageChannel),
    default=None,
)
@tj.as_slash_command('join', "Connects the bot to a voice channel")
#
@tj.with_argument('channel', converters=to_voice_or_stage_channels, default=None)
@tj.as_message_command('join', 'j', 'connect', 'co', 'con')
async def join_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    channel: Option[hk.GuildVoiceChannel | hk.GuildStageChannel],
) -> None:
    """Connect the bot to a voice channel."""

    try:
        await join_impl_precaught(ctx, lvc, channel=channel)
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


# /leave


@with_identifier(C.LEAVE)
# -
@tj.as_slash_command('leave', "Leaves the voice channel and clears the queue")
@tj.as_message_command(
    'leave', 'l', 'lv', 'dc', 'disconnect', 'discon', 'eddisntheregoaway'
)
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
    except OthersInVoice as exc:
        await err_say(
            ctx,
            content=f"🚫 Someone else is already in <#{exc.channel}>.\n **You bypass this by having the {dj_perms_fmt} permissions**",
        )
    else:
        await say(ctx, content=f"📎 ~~<#{vc}>~~")


# -


loader = conns.load_from_scope().make_loader()
