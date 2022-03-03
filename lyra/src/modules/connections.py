from src.lib.music import *
from src.lib.checks import Checks, check


conns = (
    tj.Component(name='Conections', strict=True).add_check(guild_c).set_hooks(music_h)
)


@conns.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    client: tj.Client = tj.inject(type=tj.Client),
    bot: hk.GatewayBot = tj.inject(type=hk.GatewayBot),
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
):
    def _conn():
        return lvc.get_guild_gateway_connection_info(event.guild_id)

    new = event.state
    old = event.old_state
    if not await lvc.get_guild_node(event.guild_id) or not (conn := _conn()):
        return

    assert isinstance(conn, dict)

    def _in_voice():
        return set(
            filter(
                lambda v: not v.member.is_bot,
                client.cache.get_voice_states_view_for_channel(  # type: ignore
                    event.guild_id, conn['channel_id']
                ).values(),
            )
        )

    ch = (d := await get_data(event.guild_id, lvc)).out_channel_id
    assert ch

    q = d.queue

    async def on_everyone_leaves_vc():
        logger.debug(
            f"In guild {event.guild_id} started channel {conn['channel_id']} timeout inactivity"
        )
        for _ in range(10):
            if len(_in_voice()) >= 1 or not (_conn()):
                logger.debug(
                    f"In guild {event.guild_id} stopped channel {conn['channel_id']} timeout inactivity"
                )
                return False
            await asyncio.sleep(60)

        __conn = _conn()
        assert isinstance(__conn, dict)

        await cleanups__(event.guild_id, client.shards, lvc)
        logger.info(
            f"In guild {event.guild_id} left   channel {(_vc := __conn['channel_id'])} due to inactivity"
        )
        await client.rest.create_message(
            ch, f"🍃📎 ~~<#{_vc}>~~ `(Left due to inactivity)`"
        )

        return True

    from src.lib.music import set_pause__

    in_voice = _in_voice()
    vc: int = conn['channel_id']
    bot_u = bot.get_me()
    assert bot_u
    # if new.channel_id == vc and len(in_voice) == 1 and new.user_id != bot_u.id:
    #     # Someone rejoined
    #     try:
    #         await set_pause__(event.guild_id, lvc, pause=False)
    #         await client.rest.create_message(ch, f"✨⏸️ Resumed")
    #     except NotConnected:
    #         pass

    if (new.channel_id != vc) and not in_voice:
        if old and old.channel_id == vc:
            # Everyone left

            # TODO: Should be in `playback.py`
            await set_pause__(event, lvc, pause=True, update_controller=True)
            await client.rest.create_message(ch, f"✨▶️ Paused as no one is listening")

            await asyncio.wait(
                (asyncio.create_task(on_everyone_leaves_vc()),),
                return_when=asyncio.FIRST_COMPLETED,
            )


# Join


@tj.with_channel_slash_option(
    'channel',
    "Which channel? (If not parsed, your currently connected channel)",
    types=(hk.GuildVoiceChannel,),
    default=None,
)
@tj.as_slash_command('join', "Connects the bot to a voice channel")
#
@tj.with_argument('channel', converters=tj.to_channel, default=None)
@tj.with_parser
@tj.as_message_command('join', 'j', 'connect', 'co', 'con')
async def join(
    ctx: tj.abc.Context,
    channel: hk.GuildVoiceChannel,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Connect the bot to a voice channel."""
    await join_(ctx, channel, lvc=lvc)


@check(Checks.CATCH_ALL)
async def join_(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel],
    /,
    *,
    lvc: lv.Lavalink,
):
    try:
        vc = await join__(ctx, channel, lvc)
        await reply(ctx, content=f"🖇️ <#{vc}>")
    except ChannelChange as sig:
        await reply(
            ctx, content=f"📎🖇️ ~~<#{sig.old_channel}>~~ ➜ __<#{sig.new_channel}>__"
        )
    except NotInVoice:
        await err_reply(
            ctx,
            content="❌ Please specify a voice channel or join one",
        )
    except AlreadyConnected as exc:
        await err_reply(ctx, content=f"❗ Already connected to <#{exc.channel}>")
    except InternalError:
        await err_reply(
            ctx,
            content="⁉️ Something internal went wrong. Please try again in few minutes",
        )
    except Forbidden as exc:
        await err_reply(
            ctx,
            content=f"⛔ Not sufficient permissions to join channel <#{exc.channel}>",
        )
    except TimeoutError:
        await err_reply(
            ctx,
            content="⌛ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
        )


# Leave


@tj.as_slash_command('leave', "Leaves the voice channel and clears the queue")
#
@tj.as_message_command('leave', 'l', 'lv', 'dc', 'disconnect', 'discon')
async def leave(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    await leave_(ctx, lvc=lvc)


@check(Checks.CATCH_ALL)
async def leave_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    """Stops playback of the current song."""
    assert ctx.guild_id

    try:
        vc = await leave__(ctx, lvc)
    except NotConnected:
        await err_reply(ctx, content="❗ Not currently connected yet")
    else:
        await reply(ctx, content=f"📎 ~~<#{vc}>~~")


# -


loader = conns.load_from_scope().make_loader()
