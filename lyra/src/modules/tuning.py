import typing as t
import logging
import difflib as dfflib

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv


from hikari.messages import MessageFlag as msgflag
from src.lib.music import music_h
from src.lib.utils import (
    guild_c,
    reply,
    err_reply,
    with_message_command_group_template,
)
from src.lib.errors import NotConnected
from src.lib.checks import DJ_PERMS, Checks, check
from src.lib.lavaimpl import Bands, access_equalizer


tuning = tj.Component(name='Tuning', strict=True).add_check(guild_c).set_hooks(music_h)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


async def set_mute__(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    mute: t.Optional[bool],
    respond: bool = False,
) -> None:
    assert not (ctx.cache is None or ctx.guild_id is None)
    me = ctx.cache.get_me()
    assert me is not None

    async with access_equalizer(ctx, lvc) as eq:
        if mute is None:
            mute = not eq.is_muted
        if mute and eq.is_muted:
            await err_reply(ctx, content="❗ Already muted")
            return
        if not (mute or eq.is_muted):
            await err_reply(ctx, content="❗ Already unmuted")
            return

        if mute:
            await ctx.rest.edit_member(ctx.guild_id, me, mute=True)
            msg = "🔇 Muted"
        else:
            await ctx.rest.edit_member(ctx.guild_id, me, mute=False)
            msg = "🔊 Unmuted"

        eq.is_muted = mute
        if respond:
            await reply(ctx, content=msg)


# ~


@tuning.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent, lvc: al.Injected[lv.Lavalink]
):
    try:
        async with access_equalizer(event.guild_id, lvc) as eq:
            eq.is_muted = event.state.is_guild_muted
    except NotConnected:
        return


# Volume


volume_g_s = tuning.with_slash_command(
    tj.slash_command_group('volume', "Manages the volume of this guild's player")
)


@tuning.with_message_command
@tj.as_message_command_group('volume', 'v', 'vol', strict=True)
@with_message_command_group_template
async def volume_g_m(_: tj.abc.MessageContext):
    """Manages the volume of this guild's player"""
    ...


## Volume Set


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
    lvc: al.Injected[lv.Lavalink],
):
    await volume_set_(ctx, scale, lvc=lvc)


@volume_g_m.with_command
@tj.with_argument('scale', converters=int, min_value=0, max_value=10)
@tj.with_parser
@tj.as_message_command('set', '=', '.')
async def volume_set_m(
    ctx: tj.abc.MessageContext,
    scale: int,
    lvc: al.Injected[lv.Lavalink],
):
    """
    Set the volume of the bot from 0-10
    """
    if not 0 <= scale <= 10:
        await err_reply(
            ctx,
            content=f'❌ Volume percentage must be between `0` and `10` `(got: {scale})`',
        )
        return
    await volume_set_(ctx, scale, lvc=lvc)


@check(Checks.CONN | Checks.SPEAK, perms=DJ_PERMS)
async def volume_set_(ctx: tj.abc.Context, scale: int, /, *, lvc: lv.Lavalink) -> None:
    """Set the volume of the bot from 0-10"""
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        eq.volume = scale
        await lvc.volume(ctx.guild_id, scale * 10)
        await reply(ctx, content=f"🎚️ Volume set to **`{scale}`**")


## Volume Up


@volume_g_s.with_command
@tj.with_int_slash_option(
    'amount', "Increase by how much (If not given, by 1)", default=1
)
@tj.as_slash_command('up', "Increase the bot's volume")
async def volume_up_s(
    ctx: tj.abc.SlashContext,
    amount: int,
    lvc: al.Injected[lv.Lavalink],
):
    await volume_up_(ctx, amount, lvc=lvc)


@volume_g_m.with_command
@tj.with_argument('amount', converters=int, default=1)
@tj.with_parser
@tj.as_message_command('up', 'u', '+', '^')
async def volume_up_m(
    ctx: tj.abc.MessageContext,
    amount: int,
    lvc: al.Injected[lv.Lavalink],
):
    """
    Increase the bot's volume
    """
    await volume_up_(ctx, amount, lvc=lvc)


@check(Checks.CONN | Checks.SPEAK, perms=DJ_PERMS)
async def volume_up_(ctx: tj.abc.Context, amount: int, /, *, lvc: lv.Lavalink) -> None:
    """Increase the bot's volume"""
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        old = eq.volume
        if old == 10:
            await err_reply(ctx, content=f"❗ Already maxed out the volume")
            return
        eq.up(amount)
        new = eq.volume
        await lvc.volume(ctx.guild_id, new * 10)

    await reply(ctx, content=f"🔈**`＋`** ~~`{old}`~~ ➜ **`{new}`**")
    if not 0 <= amount <= 10 - old:
        await reply(
            ctx,
            hidden=True,
            content=f"❕ *The given amount was too large; **Maxed out** the volume*",
        )


## Volume Down


@volume_g_s.with_command
@tj.with_int_slash_option(
    'amount', "Decrease by how much? (If not given, by 1)", default=1
)
@tj.as_slash_command('down', "Decrease the bot's volume")
async def volume_down_s(
    ctx: tj.abc.SlashContext,
    amount: int,
    lvc: al.Injected[lv.Lavalink],
):
    await volume_down_(ctx, amount, lvc=lvc)


@volume_g_m.with_command
@tj.with_argument('amount', converters=int, default=1)
@tj.with_parser
@tj.as_message_command('down', 'd', '-', 'v')
async def volume_down_m(
    ctx: tj.abc.MessageContext,
    amount: int,
    lvc: al.Injected[lv.Lavalink],
):
    """Decrease the bot's volume"""
    await volume_down_(ctx, amount, lvc=lvc)


@check(Checks.CONN | Checks.SPEAK, perms=DJ_PERMS)
async def volume_down_(
    ctx: tj.abc.Context, amount: int, /, *, lvc: lv.Lavalink
) -> None:
    """
    Decrease the bot's volume"
    """
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        old = eq.volume
        if old == 0:
            await err_reply(ctx, content=f"❗ Already muted the volume")
            return
        eq.down(amount)
        new = eq.volume
        await lvc.volume(ctx.guild_id, new * 10)

    await reply(ctx, content=f"🔈**`ー`** **`{new}`** ⟸ ~~`{old}`~~")
    if not 0 <= amount <= old:
        await reply(
            ctx,
            hidden=True,
            content=f"❕ *The given amount was too large; **Muted** the volume*",
        )


# Mute


@tuning.with_slash_command
@tj.as_slash_command('mute', 'Server mutes the bot')
async def mute_s(ctx: tj.abc.SlashContext, lvc: al.Injected[lv.Lavalink]):
    await mute_(ctx, lvc=lvc)


@tuning.with_message_command
@tj.as_message_command('mute', 'm')
async def mute_m(ctx: tj.abc.MessageContext, lvc: al.Injected[lv.Lavalink]):
    """
    Server mutes the bot
    """
    await mute_(ctx, lvc=lvc)


@check(Checks.CONN, perms=DJ_PERMS)
async def mute_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Server mutes the bot"""
    await set_mute__(ctx, lvc, mute=True, respond=True)


# Unmute


@tuning.with_slash_command
@tj.as_slash_command('unmute', 'Server unmutes the bot')
async def unmute_s(ctx: tj.abc.SlashContext, lvc: al.Injected[lv.Lavalink]):
    await unmute_(ctx, lvc=lvc)


@tuning.with_message_command
@tj.as_message_command('unmute', 'u', 'um')
async def unmute_m(ctx: tj.abc.MessageContext, lvc: al.Injected[lv.Lavalink]):
    """
    Server unmutes the bot
    """
    await unmute_(ctx, lvc=lvc)


@check(Checks.CONN, perms=DJ_PERMS)
async def unmute_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Server unmutes the bot"""
    await set_mute__(ctx, lvc, mute=False, respond=True)


# Mute-Unmute


@tuning.with_slash_command
@tj.as_slash_command('mute-unmute', 'Toggles between server mute and unmuting the bot')
async def mute_unmute_s(ctx: tj.abc.SlashContext, lvc: al.Injected[lv.Lavalink]):
    await mute_unmute_(ctx, lvc=lvc)


@tuning.with_message_command
@tj.as_message_command('muteunmute', 'mute-unmute', 'mm', 'mu', 'tm', 'togglemute')
async def mute_unmute_m(ctx: tj.abc.MessageContext, lvc: al.Injected[lv.Lavalink]):
    """
    Toggles between server mute and unmuting the bot
    """
    await mute_unmute_(ctx, lvc=lvc)


@check(Checks.CONN, perms=DJ_PERMS)
async def mute_unmute_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Toggles between server mute and unmuting the bot"""
    await set_mute__(ctx, lvc, mute=None, respond=True)


# Equalizer


equalizer_g_s = tuning.with_slash_command(
    tj.slash_command_group('equalizer', "Manages the bot's equalizer")
)


@tuning.with_message_command
@tj.as_message_command_group('equalizer', 'eq', strict=True)
@with_message_command_group_template
async def equalizer_g_m(_: tj.abc.MessageContext):
    """Manages the bot's equalizer"""
    ...


## Equalizer Rreset


VALID_PRESETS: dict[str, str] = {j['name']: i for i, j in Bands._load_bands().items()} | {'Flat': 'flat'}  # type: ignore


@equalizer_g_s.with_command
@tj.with_str_slash_option(
    'preset',
    "Which present?",
    choices=VALID_PRESETS,
)
@tj.as_slash_command('preset', "Sets the bot's equalizer to a preset")
async def equalizer_preset_s(
    ctx: tj.abc.SlashContext,
    preset: str,
    lvc: al.Injected[lv.Lavalink],
):
    await equalizer_preset_(ctx, preset, lvc=lvc)


@equalizer_g_m.with_command
@tj.with_argument('preset')
@tj.with_parser
@tj.as_message_command('preset', 'pre', '=')
async def equalizer_preset_m(
    ctx: tj.abc.MessageContext,
    preset: str,
    lvc: al.Injected[lv.Lavalink],
):
    """
    Sets the bot's equalizer to a preset
    """
    if preset not in VALID_PRESETS.values():
        await err_reply(
            ctx,
            del_after=10,
            content=f"❗ Invalid preset given. Must be one of the following:\n> {', '.join(('`%s (%s)`' % (j, i) for i,j in VALID_PRESETS.items()))}",
        )
        return
    await equalizer_preset_(ctx, preset, lvc=lvc)


@check(Checks.CONN | Checks.SPEAK, perms=DJ_PERMS)
async def equalizer_preset_(
    ctx: tj.abc.Context, preset: str, /, *, lvc: lv.Lavalink
) -> None:
    """Sets the bot's equalizer to a preset"""
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        bands = Bands.load(preset)
        await lvc.equalize_all(ctx.guild_id, list(bands))
        eq.bands = bands
    await reply(ctx, content=f"🎛️ Equalizer set to preset: `{preset.capitalize()}`")


# -


loader = tuning.make_loader()
