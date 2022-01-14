from src.lib.music import *


tuning = tj.Component(checks=(guild_c,), hooks=music_h)


# Volume


volume_g_s = tuning.with_slash_command(
    tj.slash_command_group('volume', "Manages the volume of this guild's player")
)


@tuning.with_message_command
@tj.as_message_command_group('volume', 'v', strict=True)
async def volume_g_m(ctx: tj.abc.MessageContext):
    """
    Manages the volume of this guild's player
    """
    cmd = ctx.command
    assert isinstance(cmd, tj.abc.MessageCommandGroup)
    p = next(iter(ctx.client.prefixes))
    cmd_n = next(iter(cmd.names))
    sub_cmds_n = map(lambda s: next(iter(s.names)), cmd.commands)
    valid_cmds = ', '.join(f"`{p}{cmd_n} {sub_cmd_n} ...`" for sub_cmd_n in sub_cmds_n)
    await err_reply(
        ctx,
        content=f"❌ This is a command group. Use the following instead:\n{valid_cmds}",
    )


## volume set


@volume_g_s.with_command
@tj.with_int_slash_option(
    'scale',
    "The volume scale? [Need to be between 0 and 10]",
    choices={str(i): i for i in range(10, -1, -1)},
)
@tj.as_slash_command('set', "Set the volume of the bot from 0-10")
async def volume_set_s(
    ctx: tj.abc.SlashContext,
    scale: int,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await volume_set_(ctx, scale, lvc=lvc)


@volume_g_m.with_command
@tj.with_argument('scale', converters=int)
@tj.with_parser
@tj.as_message_command('set', '=', '.')
async def volume_set_m(
    ctx: tj.abc.MessageContext,
    scale: int,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    """
    Set the volume of the bot from 0-10
    """
    if not 0 <= scale <= 10:
        await err_reply(
            ctx,
            content=f'❗ Volume percentage must be between `0` and `10` `(got: {scale})`',
        )
        return
    await volume_set_(ctx, scale, lvc=lvc)


@check(Checks.CONN, DJ_PERMS)
async def volume_set_(ctx: tj.abc.Context, scale: int, lvc: lv.Lavalink) -> None:
    """
    Set the volume of the bot from 0-10
    """
    assert ctx.guild_id is not None

    async with access_equalizer(ctx, lvc) as eq:
        eq.volume = scale * 10
        await lvc.volume(ctx.guild_id, scale * 10)
        await reply(ctx, content=f"🎚️ Volume set to **`{scale}`**")


# Mute


@tuning.with_slash_command
@tj.as_slash_command('mute', 'Server mutes the bot')
async def mute_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await mute_(ctx, lvc=lvc)


@tuning.with_message_command
@tj.as_message_command('mute', 'm')
async def mute_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    """
    Server mutes the bot
    """
    await mute_(ctx, lvc=lvc)


@check(Checks.CONN, DJ_PERMS)
async def mute_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """
    Server mutes the bot
    """
    await set_mute__(ctx, lvc, mute=True, respond=True)


# Unmute


@tuning.with_slash_command
@tj.as_slash_command('unmute', 'Server unmutes the bot')
async def unmute_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await unmute_(ctx, lvc=lvc)


@tuning.with_message_command
@tj.as_message_command('unmute', 'u')
async def unmute_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    """
    Server unmutes the bot
    """
    await unmute_(ctx, lvc=lvc)


@check(Checks.CONN, DJ_PERMS)
async def unmute_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """
    Server unmutes the bot
    """
    await set_mute__(ctx, lvc, mute=False, respond=True)


# Mute-Unmute


@tuning.with_slash_command
@tj.as_slash_command('mute-unmute', 'Toggles between server mute and unmuting the bot')
async def mute_unmute_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await mute_unmute_(ctx, lvc=lvc)


@tuning.with_message_command
@tj.as_message_command('muteunmute', 'mute-unmute', 'mm', 'mu', 'tm', 'togglemute')
async def mute_unmute_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    """
    Toggles between server mute and unmuting the bot
    """
    await mute_unmute_(ctx, lvc=lvc)


@check(Checks.CONN, DJ_PERMS)
async def mute_unmute_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
    """
    Toggles between server mute and unmuting the bot
    """
    await set_mute__(ctx, lvc, mute=None, respond=True)


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(tuning.copy())
