import hikari as hk
import tanjun as tj
import alluka as al


from hikari.permissions import Permissions as hkperms
from src.lib.music import music_h
from src.lib.checks import Checks, check
from src.lib.utils import (
    GuildConfig,
    guild_c,
    with_message_command_group_template,
    reply,
    err_reply,
)


config = tj.Component(name='Config', strict=True).add_check(guild_c).set_hooks(music_h)


## config prefix


guildconfig_g_s = config.with_slash_command(
    tj.slash_command_group('guild-config', "Manage the bot's guild-specific settings")
)


prefix_sg_s = guildconfig_g_s.with_command(
    tj.slash_command_group('prefix', "Manages the bot's prefixes")
)


@config.with_message_command
@tj.as_message_command_group(
    'guildconfig', 'con', 'config', 'gc', 'settings', 'k', 'cfg', strict=True
)
@with_message_command_group_template
async def guildconfig_g_m(_: tj.abc.MessageContext):
    """Manage the bot's guild-specific settings"""
    ...


@guildconfig_g_m.with_command
@tj.as_message_command_group('prefix', 'pref', 'prf', '/', strict=True)
@with_message_command_group_template
async def prefix_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's prefixes"""
    ...


### config prefix list


@prefix_sg_s.with_command
@tj.as_slash_command('list', "Lists all usable of the bot")
async def prefix_list_s(ctx: tj.abc.SlashContext, cfg: al.Injected[GuildConfig]):
    await prefix_list_(ctx, cfg=cfg)


@prefix_sg_m.with_command
@tj.as_message_command('list', 'l', '.')
async def prefix_list_m(ctx: tj.abc.MessageContext, cfg: al.Injected[GuildConfig]):
    """
    Lists all usable prefixes of the bot
    """
    await prefix_list_(ctx, cfg=cfg)


async def prefix_list_(ctx: tj.abc.Context, /, *, cfg: GuildConfig) -> None:
    """Lists all usable prefixes of the bot"""
    assert ctx.guild_id

    g_prefixes: list[str] = cfg[str(ctx.guild_id)].setdefault('prefixes', [])

    embed = hk.Embed(title='「／」 All usable prefixes')
    embed.add_field(
        'Global', '\n'.join('`%s`' % prf for prf in ctx.client.prefixes), inline=True
    )
    embed.add_field(
        'Guild-specific',
        '\n'.join('`%s`' % prf for prf in g_prefixes) or '```diff\n--\n```',
        inline=True,
    )
    await reply(ctx, embed=embed)


### config prefix add


@prefix_sg_s.with_command
@tj.with_str_slash_option('prefix', "What prefix?")
@tj.as_slash_command('add', "Adds a new prefix of the bot for this guild")
async def prefix_add_s(
    ctx: tj.abc.SlashContext,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    await prefix_add_(ctx, prefix, cfg=cfg)


@prefix_sg_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('add', '+', 'a', 'new', 'create', 'n')
async def prefix_add_m(
    ctx: tj.abc.MessageContext,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    """
    Adds a new prefix of the bot for this guild
    """
    await prefix_add_(ctx, prefix, cfg=cfg)


@check(perms=hkperms.ADMINISTRATOR)
async def prefix_add_(ctx: tj.abc.Context, prefix: str, /, *, cfg: GuildConfig) -> None:
    """Adds a new prefix of the bot for this guild"""
    assert ctx.guild_id

    g_prefixes: list[str] = cfg[str(ctx.guild_id)].setdefault('prefixes', [])

    if prefix in g_prefixes + list(ctx.client.prefixes):
        await err_reply(ctx, content=f"❗ Already defined this prefix")
        return

    cfg[str(ctx.guild_id)]['prefixes'].append(prefix)
    await reply(
        ctx, content=f"**`「／」+`** Added `{prefix}` as a new prefix for this guild"
    )


### config prefix remove


@prefix_sg_s.with_command
@tj.with_str_slash_option('prefix', "Which prefix?")
@tj.as_slash_command('remove', "Removes an existing prefix of the bot for this guild")
async def prefix_remove_s(
    ctx: tj.abc.SlashContext,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    await prefix_remove_(ctx, prefix, cfg=cfg)


@prefix_sg_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('remove', '-', 'rem', 'r', 'rm', 'd', 'del', 'delete')
async def prefix_remove_m(
    ctx: tj.abc.MessageContext,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    """
    Removes an existing prefix of the bot for this guild
    """
    await prefix_remove_(ctx, prefix, cfg=cfg)


@check(perms=hkperms.ADMINISTRATOR)
async def prefix_remove_(
    ctx: tj.abc.Context, prefix: str, /, *, cfg: GuildConfig
) -> None:
    """Removes an existing prefix of the bot for this guild"""
    assert ctx.guild_id
    g_prefixes: list[str] = cfg[str(ctx.guild_id)].setdefault('prefixes', [])

    if prefix in ctx.client.prefixes:
        await err_reply(ctx, content=f"❌ This prefix is global and cannot be removed")
        return

    elif prefix not in g_prefixes:
        await err_reply(ctx, content=f"❗ No such prefix found")
        return

    g_prefixes.remove(prefix)
    await reply(ctx, content=f"**`「／」ー`** Removed the prefix `{prefix}` for this guild")


## guildconfig nowplayingmsg


nowplayingmsg_sg_s = guildconfig_g_s.with_command(
    tj.slash_command_group('now-playing-msg', "Manages the bot's now playing messages")
)


@guildconfig_g_m.with_command
@tj.as_message_command_group(
    'nowplayingmsg', 'now-playing-msg', 'npmsg', 'np', strict=True
)
@with_message_command_group_template
async def nowplayingmsg_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's now playing messages"""
    ...


### guildconfig nowplayingmsg toggle


@nowplayingmsg_sg_s.with_command
@tj.as_slash_command(
    'toggle', "Toggles the now playing messages to be automatically sent or not"
)
async def nowplayingmsg_toggle_s(
    ctx: tj.abc.SlashContext, cfg: al.Injected[GuildConfig]
):
    await nowplayingmsg_toggle_(ctx, cfg=cfg)


@nowplayingmsg_sg_m.with_command
@tj.with_parser
@tj.as_message_command('toggle', 'tggl', '.')
async def nowplayingmsg_toggle_m(
    ctx: tj.abc.MessageContext, cfg: al.Injected[GuildConfig]
):
    """
    Toggles the now playing messages to be automatically sent or not
    """
    await nowplayingmsg_toggle_(ctx, cfg=cfg)


@check(perms=hkperms.MANAGE_GUILD)
async def nowplayingmsg_toggle_(ctx: tj.abc.Context, /, *, cfg: GuildConfig) -> None:
    """Toggles the now playing messages to be automatically sent or not"""
    assert ctx.guild_id
    send_np_msg: bool = cfg[str(ctx.guild_id)].setdefault('send_nowplaying_msg', False)

    cfg[str(ctx.guild_id)]['send_nowplaying_msg'] = not send_np_msg
    msg = (
        "🔕 Not sending now playing messages from now on"
        if send_np_msg
        else "🔔 Sending now playing messages from now on"
    )
    await reply(ctx, content=msg)


# -


loader = config.make_loader()
