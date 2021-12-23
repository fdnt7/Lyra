from src.lib.music import *


conns = tj.Component(checks=(guild_c,), hooks=music_h)


# Join


@conns.with_slash_command
@tj.with_channel_slash_option(
    "channel",
    "Which channel? (If not parsed, your currently connected channel)",
    types=(hk.GuildVoiceChannel,),
    default=None,
)
@tj.as_slash_command("join", "Connects the bot to a voice channel")
async def join_s(
    ctx: tj.abc.SlashContext,
    channel: hk.GuildVoiceChannel,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await join_(ctx, channel, lvc=lvc)


@conns.with_message_command
@tj.with_argument("channel", converters=tj.to_channel, default=None)
@tj.with_parser
@tj.as_message_command("join", "j", "connect")
async def join_m(
    ctx: tj.abc.MessageContext,
    channel: hk.GuildVoiceChannel,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Connect the bot to a voice channel."""
    await join_(ctx, channel, lvc=lvc)


@check(Checks.CATCH_ALL)
async def join_(
    ctx: tj.abc.Context,
    channel: t.Optional[hk.GuildVoiceChannel],
    lvc: lv.Lavalink,
):
    try:
        if voice_channel := await join__(ctx, channel, lvc):
            await reply(ctx, content=f"🖇️ <#{voice_channel}>")
    except ChannelChange as sig:
        await reply(
            ctx, content=f"🔗 ~~<#{sig.old_channel}>~~ ➜ __<#{sig.new_channel}>__"
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
    except TimeoutError:
        await def_reply(
            ctx,
            content="⏳ Took too long to join voice. **Please make sure the bot has access to the specified channel**",
        )
    except ConnectionForbidden as exc:
        await err_reply(
            ctx,
            content=f"⛔ Not sufficient permissions to join channel <#{exc.channel}>",
        )


# Leave


@conns.with_slash_command
@tj.as_slash_command("leave", "Leaves the voice channel and clears the queue")
async def leave_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await leave_(ctx, lvc=lvc)


@conns.with_message_command
@tj.as_message_command("leave", "l", "dc")
async def leave_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Leaves the voice channel and clears the queue."""
    await leave_(ctx, lvc=lvc)


@check(Checks.CATCH_ALL)
async def leave_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    """Stops playback of the current song."""
    assert ctx.guild_id is not None

    if conn := await lvc.get_guild_gateway_connection_info(ctx.guild_id):
        assert isinstance(conn, dict)
        curr_channel = conn["channel_id"]

        await check_others_not_in_vc__(ctx, DJ_PERMS, conn)

        async with access_queue(ctx, lvc) as q:
            q.clr()

        await lvc.destroy(ctx.guild_id)
        if ctx.client.shards:
            # Set voice channel to None
            await ctx.client.shards.update_voice_state(ctx.guild_id, None)
            await lvc.wait_for_connection_info_remove(ctx.guild_id)

        # We must manually remove the node and queue loop from lavasnek
        await lvc.remove_guild_node(ctx.guild_id)
        await lvc.remove_guild_from_loops(ctx.guild_id)

        return await reply(ctx, content=f"📎 <#{curr_channel}>")

    await err_reply(ctx, content="❗ Not currently connected yet")


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(conns.copy())
