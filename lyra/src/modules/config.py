import typing as t

import hikari as hk
import tanjun as tj
import alluka as al


from hikari.permissions import Permissions as hkperms
from src.lib.extras import uniquify
from src.lib.music import music_h
from src.lib.checks import check
from src.lib.utils import (
    GuildConfig,
    guild_c,
    with_message_command_group_template,
    reply,
    err_reply,
)


config = tj.Component(name='Config', strict=True).add_check(guild_c).set_hooks(music_h)

RESTRICTOR = hkperms.MANAGE_CHANNELS | hkperms.MANAGE_ROLES


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
# -
@prefix_sg_m.with_command
@tj.as_message_command('list', 'l', '.')
async def prefix_list_(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]) -> None:
    """Lists all usable prefixes of the bot"""
    assert ctx.guild_id

    g_prefixes: list[str] = cfg[str(ctx.guild_id)].setdefault('prefixes', [])

    embed = hk.Embed(title='「／」 All usable prefixes')
    embed.add_field(
        'Global', '\n'.join('`%s`' % prf for prf in ctx.client.prefixes), inline=True
    )
    embed.add_field(
        'Guild-specific',
        '\n'.join('`%s`' % prf for prf in g_prefixes) or '```diff\n-Empty-\n```',
        inline=True,
    )
    await reply(ctx, embed=embed)


### config prefix add


@prefix_sg_s.with_command
@tj.with_str_slash_option('prefix', "What prefix?")
@tj.as_slash_command('add', "Adds a new prefix of the bot for this guild")
# -
@prefix_sg_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('add', '+', 'a', 'new', 'create', 'n')
async def prefix_add_(
    ctx: tj.abc.Context,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    """
    Adds a new prefix of the bot for this guild
    """
    await _prefix_add(ctx, prefix, cfg=cfg)


@check(perms=hkperms.ADMINISTRATOR)
async def _prefix_add(ctx: tj.abc.Context, prefix: str, /, *, cfg: GuildConfig) -> None:
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
# -
@prefix_sg_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('remove', '-', 'rem', 'r', 'rm', 'd', 'del', 'delete')
async def prefix_remove_(
    ctx: tj.abc.Context,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    """
    Removes an existing prefix of the bot for this guild
    """
    await _prefix_remove(ctx, prefix, cfg=cfg)


@check(perms=hkperms.ADMINISTRATOR)
async def _prefix_remove(
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
# -
@nowplayingmsg_sg_m.with_command
@tj.as_message_command('toggle', 'tggl', 't')
async def nowplayingmsg_toggle(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    await _nowplayingmsg_toggle(ctx, cfg=cfg)


@check(perms=hkperms.MANAGE_GUILD)
async def _nowplayingmsg_toggle(ctx: tj.abc.Context, /, *, cfg: GuildConfig) -> None:
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


## guildconfig restricts


restricts_sg_s = guildconfig_g_s.with_command(
    tj.slash_command_group(
        'restricts', "Manages the bot's restricted channels, roles and members"
    )
)


@guildconfig_g_m.with_command
@tj.as_message_command_group(
    'restricts', 'restrict', 'restr', 'rest', 'rst', 'r', strict=True
)
@with_message_command_group_template
async def restricts_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's restricted channels, roles and members"""
    ...


@restricts_sg_m.with_command
@tj.as_message_command('list', 'ls', 'l', 'a', 'all', '/')
# -
@restricts_sg_s.with_command
@tj.as_slash_command(
    'list', "Shows the current whitelisted/blacklisted channels, roles and members"
)
async def restricts_list_(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    assert ctx.guild_id
    whitelisted: bool = cfg[str(ctx.guild_id)].setdefault('whitelisted', False)
    e, c, C = ('✔️', 'white', 0xFFFFFF) if whitelisted else ('❌', 'black', 0x000000)

    restricts: dict[str, tuple[int]] = cfg[str(ctx.guild_id)].setdefault(
        c + "lists", {}
    )
    embed = (
        hk.Embed(
            title=f"📝{e} All {c}listed channels, roles and members",
            color=C,
        )
        .add_field(
            f"{c}listed channels".capitalize(),
            '\n'.join(f'<#{r}>' for r in restricts.get('channels', []))
            or '```diff\n-Empty-\n```',
        )
        .add_field(
            f"{c}listed roles".capitalize(),
            '\n'.join(f'<@&{r}>' for r in restricts.get('roles', []))
            or '```diff\n-Empty-\n```',
        )
        .add_field(
            f"{c}listed members".capitalize(),
            '\n'.join(f'<@{r}>' for r in restricts.get('users', []))
            or '```diff\n-Empty-\n```',
        )
    )

    await reply(ctx, embed=embed)


@restricts_sg_m.with_command
@tj.as_message_command('toggle', 'tggl', '.')
# -
@restricts_sg_s.with_command
@tj.as_slash_command(
    'toggle', "Toggles the bot restriction mode to be whitelisted or blacklisted"
)
async def channels_toggle_(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    await _channels_toggle(ctx, cfg=cfg)


@check(perms=RESTRICTOR)
async def _channels_toggle(ctx: tj.abc.Context, /, *, cfg: GuildConfig):
    assert ctx.guild_id
    whitelisted: bool = cfg[str(ctx.guild_id)].setdefault('whitelisted', False)

    cfg[str(ctx.guild_id)]['whitelisted'] = not whitelisted
    msg = (
        "📝✔️ Toggled to whitelist mode"
        if not whitelisted
        else "📝❌ Toggled to blacklist mode"
    )
    await reply(ctx, content=msg)


blacklist_sg_s = guildconfig_g_s.with_command(
    tj.slash_command_group(
        'blacklist', "Manages the bot's blacklisted channels, roles and users"
    )
)


@guildconfig_g_m.with_command
@tj.as_message_command_group('blacklist', 'bl', 'x', '-', strict=True)
async def blacklist_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's blacklisted channels, roles and users"""
    ...


@blacklist_sg_m.with_command
@tj.with_multi_argument('mentionables', (tj.to_channel, tj.to_role, tj.to_user))
@tj.with_parser
@tj.as_message_command('add', '+', 'a')
async def blacklist_add_m(
    ctx: tj.abc.MessageContext,
    mentionables: t.Collection[hk.TextableGuildChannel | hk.Role | hk.Member],
    cfg: al.Injected[GuildConfig],
):
    await _blacklist_add(ctx, mentionables, cfg=cfg)


@blacklist_sg_s.with_command
@tj.with_mentionable_slash_option('mentionable', "Blacklist which member/channel/role?")
@tj.as_slash_command('add', "Add a channel, role or member to the blacklists")
async def blacklist_add_s(
    ctx: tj.abc.SlashContext,
    mentionable: hk.TextableGuildChannel | hk.Role | hk.InteractionMember,
    cfg: al.Injected[GuildConfig],
):
    await _blacklist_add(
        ctx,
        [
            mentionable,
        ],
        cfg=cfg,
    )


@check(perms=RESTRICTOR)
async def _blacklist_add(
    ctx: tj.abc.Context,
    mentionables: t.Collection[hk.TextableChannel | hk.Role | hk.Member],
    /,
    *,
    cfg: GuildConfig,
):
    import copy

    assert ctx.guild_id
    blacklists: dict[str, list[int]] = cfg[str(ctx.guild_id)].setdefault(
        'blacklists', {}
    )
    bl_updated = copy.deepcopy(blacklists)

    updated_channels = bl_updated.setdefault('channels', [])
    updated_roles = bl_updated.setdefault('roles', [])
    updated_users = bl_updated.setdefault('users', [])

    for u in uniquify(mentionables):
        if (u_id := u.id) in updated_channels + updated_roles + updated_users:
            continue
        if isinstance(u, hk.PartialChannel):
            updated_channels.append(u_id)
        elif isinstance(u, hk.Role):
            updated_roles.append(u_id)
        else:
            updated_users.append(u_id)

    delta_ch = {*updated_channels} - {*blacklists.setdefault('channels', [])}
    delta_r = {*updated_roles} - {*blacklists.setdefault('roles', [])}
    delta_u = {*updated_users} - {*blacklists.setdefault('users', [])}

    delta_msg = ''.join(
        (
            f"**`{len(delta_ch)}`** new channels" if delta_ch else '',
            f"`{len(delta_r)}` new roles" if delta_r else '',
            f"{len(delta_u)} new users" if delta_u else '',
        )
    )
    blacklists |= bl_updated

    msg = (
        "📝❌**`+`** Added " + delta_msg
        if delta_msg
        else "❕📝❌ No new blacklists were added as it's already been assigned"
    )

    await reply(ctx, content=msg)


# -


loader = config.make_loader()
