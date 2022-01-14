from src.lib.music import *

conns = tj.Component(checks=(guild_c,), hooks=music_h)


# Join


@conns.with_slash_command
@tj.with_channel_slash_option(
    'channel',
    "Which channel? (If not parsed, your currently connected channel)",
    types=(hk.GuildVoiceChannel,),
    default=None,
)
@tj.as_slash_command('join', "Connects the bot to a voice channel")
async def join_s(
    ctx: tj.abc.SlashContext,
    channel: hk.GuildVoiceChannel,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await join_(ctx, channel, lvc=lvc)


@conns.with_message_command
@tj.with_argument('channel', converters=tj.to_channel, default=None)
@tj.with_parser
@tj.as_message_command('join', 'j', 'connect')
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
        vc = await join__(ctx, channel, lvc)
        await reply(ctx, content=f"🖇️ <#{vc}>")
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
    except Forbidden as exc:
        await err_reply(
            ctx,
            content=f"⛔ Not sufficient permissions to join channel <#{exc.channel}>",
        )


# Leave


@conns.with_slash_command
@tj.as_slash_command('leave', "Leaves the voice channel and clears the queue")
async def leave_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await leave_(ctx, lvc=lvc)


@conns.with_message_command
@tj.as_message_command('leave', 'l', 'dc')
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

    try:
        vc = await leave__(ctx, lvc)
    except NotConnected:
        await err_reply(ctx, content="❗ Not currently connected yet")
    else:
        return await reply(ctx, content=f"📎 ~~<#{vc}>~~")


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(conns.copy())
