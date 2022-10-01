import typing as t

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv
import tanjun.annotations as ja

from ..lib.extras import Option, Panic
from ..lib.errors import NotConnectedError
from ..lib.utils import (
    DJ_PERMS,
    say,
    err_say,
    with_annotated_args_wrapped,
    with_message_command_group_template,
)
from ..lib.cmd import (
    CommandIdentifier as C,
    Checks,
    with_cmd_composer,
    with_identifier,
)
from ..lib.lava import Bands, get_data, access_equalizer
from ..lib.music import __init_component__


tuning = __init_component__(__name__)


# ~


def to_preset(value: str, /) -> Panic[str]:
    if value.casefold() not in valid_presets.values():
        valid_presets_fmt = ', '.join(
            ('\"%s\" (%s)' % (j, i) for i, j in valid_presets.items())
        )
        raise ValueError(
            f"Invalid preset given. Must be one of the following:\n> {valid_presets_fmt}"
        )
    return value


async def set_mute(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    *,
    mute: Option[bool],
    respond: bool = False,
) -> None:
    assert not (ctx.cache is None or ctx.guild_id is None)
    me = ctx.cache.get_me()
    assert me is not None

    async with access_equalizer(ctx, lvc) as eq:
        if mute is None:
            mute = not eq.is_muted
        if mute and eq.is_muted:
            await err_say(ctx, content="❗ Already muted")
            return
        if not (mute or eq.is_muted):
            await err_say(ctx, content="❗ Already unmuted")
            return

        if mute:
            await ctx.rest.edit_member(ctx.guild_id, me, mute=True)
            msg = "🔇 Muted"
        else:
            await ctx.rest.edit_member(ctx.guild_id, me, mute=False)
            msg = "🔊 Unmuted"

        eq.is_muted = mute
        if respond:
            await say(ctx, content=msg)


with_common_cmd_check = with_cmd_composer(checks=Checks.CONN, perms=DJ_PERMS)
with_stage_cmd_check = with_cmd_composer(
    checks=Checks.CONN | Checks.SPEAK, perms=DJ_PERMS
)


@tuning.with_listener()
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    bot: al.Injected[hk.GatewayBot],
    lvc: al.Injected[lv.Lavalink],
):
    try:
        out_ch = (await get_data(event.guild_id, lvc)).out_channel_id
        assert out_ch

        async with access_equalizer(event.guild_id, lvc) as eq:
            if eq.is_muted != event.state.is_guild_muted:
                eq.is_muted = event.state.is_guild_muted
                await bot.rest.create_message(
                    out_ch,
                    f"❕{'🔇' if eq.is_muted else '🔊'} `(Bot was forcefully {'muted' if eq.is_muted else 'unmuted'})`",
                )
    except NotConnectedError:
        return


# /volume


@with_annotated_args_wrapped
@with_identifier(C.VOLUME)
# -
@tj.as_message_command_group('volume', 'v', 'vol', strict=True)
@with_message_command_group_template
async def volume_g_m(_: tj.abc.MessageContext):
    """Manages the volume of this guild's player"""
    ...


volume_g_s = with_identifier(C.VOLUME)(
    tj.slash_command_group('volume', "Manages the volume of this guild's player")
)


## /volume set


@with_annotated_args_wrapped
@with_stage_cmd_check(C.VOLUME_SET)
# -
@volume_g_m.as_sub_command('set', '=', '.')
@volume_g_s.as_sub_command('set', "Set the volume of the bot from 0-10")
async def volume_set_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    scale: t.Annotated[
        ja.Ranged[0, 10],
        "The volume scale? [Need to be between 0 and 10]",
    ],
):
    """
    Set the volume of the bot from 0-10
    """
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        eq.volume = scale
        await lvc.volume(ctx.guild_id, scale * 10)
        await say(ctx, content=f"🎚️ Volume set to **`{scale}`**")


## /volume up


@with_annotated_args_wrapped
@with_stage_cmd_check(C.VOLUME_UP)
# -
@volume_g_m.as_sub_command('up', 'u', '+', '^')
@volume_g_s.as_sub_command('up', "Increase the bot's volume")
async def volume_up_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    amount: t.Annotated[
        ja.Positional[ja.Int], "Increase by how much (If not given, by 1)"
    ] = 1,
):
    """
    Increase the bot's volume
    """
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        old = eq.volume
        if old == 10:
            await err_say(ctx, content=f"❗ Already maxed out the volume")
            return
        eq.up(amount)
        new = eq.volume
        await lvc.volume(ctx.guild_id, new * 10)

    await say(ctx, content=f"🔈**`＋`** ~~`{old}`~~ ➜ **`{new}`**")
    if not 0 <= amount <= 10 - old:
        await say(
            ctx,
            hidden=True,
            content=f"❕ *The given amount was too large; **Maxed out** the volume*",
        )


## /volume down


@with_annotated_args_wrapped
@with_stage_cmd_check(C.VOLUME_DOWN)
# -
@volume_g_m.as_sub_command('down', 'd', '-', 'v')
@volume_g_s.as_sub_command('down', "Decrease the bot's volume")
async def volume_down_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    amount: t.Annotated[
        ja.Positional[ja.Int], "Decrease by how much? (If not given, by 1)"
    ] = 1,
):
    """
    Decrease the bot's volume"
    """
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        old = eq.volume
        if old == 0:
            await err_say(ctx, content=f"❗ Already muted the volume")
            return
        eq.down(amount)
        new = eq.volume
        await lvc.volume(ctx.guild_id, new * 10)

    await say(ctx, content=f"🔈**`ー`** **`{new}`** ⟸ ~~`{old}`~~")
    if not 0 <= amount <= old:
        await say(
            ctx,
            hidden=True,
            content=f"❕ *The given amount was too large; **Muted** the volume*",
        )


# /mute


@with_common_cmd_check(C.MUTE)
# -
@tj.as_slash_command('mute', 'Server mutes the bot')
@tj.as_message_command('mute', 'm')
async def mute_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    """
    Server mutes the bot
    """
    await set_mute(ctx, lvc, mute=True, respond=True)


# /unmute


@with_common_cmd_check(C.UNMUTE)
# -
@tj.as_slash_command('unmute', 'Server unmutes the bot')
@tj.as_message_command('unmute', 'u', 'um')
async def unmute_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    """
    Server unmutes the bot
    """
    await set_mute(ctx, lvc, mute=False, respond=True)


# /mute-unmute


@with_common_cmd_check(C.MUTEUNMMUTE)
# -
@tj.as_slash_command('mute-unmute', 'Toggles between server mute and unmuting the bot')
@tj.as_message_command('mute-unmute', 'muteunmute', 'mm', 'mu', 'tm', 'togglemute')
async def mute_unmute_(ctx: tj.abc.Context, lvc: al.Injected[lv.Lavalink]):
    """
    Toggles between server mute and unmuting the bot
    """
    await set_mute(ctx, lvc, mute=None, respond=True)


# /equalizer


@with_identifier(C.EQUALIZER)
# -
@tj.as_message_command_group('equalizer', 'eq', strict=True)
@with_message_command_group_template
async def equalizer_g_m(_: tj.abc.MessageContext):
    """Manages the bot's equalizer"""
    ...


equalizer_g_s = with_identifier(C.EQUALIZER)(
    tj.slash_command_group('equalizer', "Manages the bot's equalizer")
)


## /equalizer preset


valid_presets: t.Final[dict[str, str]] = t.cast(
    dict[str, str],
    {
        j['name']: i
        for i, j in Bands._load_bands().items()  # pyright: ignore [reportPrivateUsage]
    },
) | {'Flat': 'flat'}


@with_annotated_args_wrapped
@with_stage_cmd_check(C.EQUALIZER_PRESET)
# -
@equalizer_g_m.as_sub_command('preset', 'pre', '=')
@equalizer_g_s.as_sub_command('preset', "Sets the bot's equalizer to a preset")
async def equalizer_preset_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
    preset: t.Annotated[
        ja.Converted[to_preset], "Which preset?", ja.Choices(valid_presets)
    ],
):
    """
    Sets the bot's equalizer to a preset
    """
    assert ctx.guild_id

    async with access_equalizer(ctx, lvc) as eq:
        bands = Bands.load(preset)
        await lvc.equalize_all(ctx.guild_id, [*bands])
        eq.bands = bands
    await say(ctx, content=f"🎛️ Equalizer set to preset: `{preset.capitalize()}`")


# -


loader = tuning.load_from_scope().make_loader()
