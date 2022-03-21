import typing as t

import hikari as hk
import tanjun as tj
import alluka as al


from hikari.permissions import Permissions as hkperms
from src.lib.extras import flatten, fmt_str, join_and, uniquify, split_preset
from src.lib.music import music_h
from src.lib.checks import check
from src.lib.utils import (
    GuildConfig,
    MentionableType,
    guild_c,
    with_message_command_group_template,
    say,
    err_say,
)


config = tj.Component(name='Config', strict=True).add_check(guild_c).set_hooks(music_h)

RESTRICTOR = hkperms.MANAGE_CHANNELS | hkperms.MANAGE_ROLES

valid_mentionables: t.Final = {'Channels': 'ch', 'Roles': 'r', 'Members': 'u'}
inv_mentionables: t.Final = {v: k for k, v in valid_mentionables.items()}

all_mentionable_categories = split_preset(
    'channels|channel|chan|ch|c,roles|role|rle|r,users|user|members|member|usr|mbr|u|m'
)


def _c(b: t.Literal[-1, 0, 1]):
    return 'Whitelisted' if b == 1 else ('Blacklisted' if b == -1 else 'N/A')


def _e(b: t.Literal[-1, 0, 1]):
    return '✅' if b == 1 else ('❌' if b == -1 else '❔')


def to_mentionable_category(value: str):
    str_ = value.casefold()
    if str_ in all_mentionable_categories[0]:
        return 'ch'
    if str_ in all_mentionable_categories[1]:
        return 'r'
    if str_ in all_mentionable_categories[2]:
        return 'u'
    raise ValueError(
        f"Invalid category given. Must be one of the following:\n> {fmt_str(flatten(all_mentionable_categories))}"
    )


async def restrict_mode_set(
    ctx: tj.abc.Context,
    cfg: GuildConfig,
    /,
    *,
    category: str,
    mode: t.Literal[-1, 0, 1] = 0,
    wipe: bool = False,
):
    assert ctx.guild_id
    g_cfg = cfg[str(ctx.guild_id)]
    cat_name = inv_mentionables[category]
    mode_name = _c(mode)

    res: dict[str, t.Any] = g_cfg.setdefault('restricted_%s' % category, {})
    if res.get('wl_mode', 0) == mode:
        await say(
            ctx,
            hidden=True,
            content=f"❕ Already set {cat_name.lower()} restricted mode to *{mode_name}*",
        )
        return
    res['wl_mode'] = mode
    if wipe:
        res.setdefault('all', []).clear()

    if mode == 0:
        msg = f"📝{_e(mode)}{'🧹' if wipe else ''} Cleared {cat_name.lower()} restriction mode{' and cleared all channels, roles and members from the restricted list' if wipe else ''}"
    else:
        msg = f"📝{_e(mode)} Set *{cat_name.lower()}* restriction mode to **`{mode_name}`**"

    await say(ctx, content=msg)


async def restrict_list_edit(
    ctx: tj.abc.Context,
    cfg: GuildConfig,
    /,
    *,
    mentionables: t.Collection[MentionableType],
    mode: t.Literal['+', '-'],
):
    assert ctx.guild_id
    g_cfg = cfg[str(ctx.guild_id)]

    res_ch = g_cfg.setdefault('restricted_ch', {})
    res_r = g_cfg.setdefault('restricted_r', {})
    res_u = g_cfg.setdefault('restricted_u', {})

    res_ch_all: list[int] = res_ch.setdefault('all', [])
    res_r_all: list[int] = res_r.setdefault('all', [])
    res_u_all: list[int] = res_u.setdefault('all', [])

    ch_wl = res_ch.get('wl_mode', 0)
    r_wl = res_r.get('wl_mode', 0)
    u_wl = res_u.get('wl_mode', 0)

    new_ch: list[int] = []
    new_r: list[int] = []
    new_u: list[int] = []

    for u in uniquify(mentionables):
        u_in_list = (u_id := u.id) in res_ch_all + res_r_all + res_u_all
        if u_in_list if mode == '+' else not u_in_list:
            continue
        if isinstance(u, hk.PartialChannel):
            new_ch.append(u_id)
        elif isinstance(u, hk.Role):
            new_r.append(u_id)
        else:
            new_u.append(u_id)

    delta_act = '**`＋`** Added' if mode == '+' else '**`ー`** Removed'
    delta_txt = 'new' if mode == '+' else 'restricted'
    delta_txt_skipped = (
        "❕📝 No new restricted channels, roles or members were added as they've already been assigned"
        if mode == '+'
        else "❕📝 No existing restricted channels, roles or members were removed as they weren't in the list"
    )
    deltas_msg = join_and(
        (
            f"**`{len(new_ch)}`** {delta_txt} channel(s) *({_c(res_ch.get('wl_mode', 0))})*"
            if new_ch
            else '',
            f"**`{len(new_r)}`** {delta_txt} role(s) *({_c(res_r.get('wl_mode', 0))})*"
            if new_r
            else '',
            f"**`{len(new_u)}`** {delta_txt} member(s) *({_c(res_u.get('wl_mode', 0))})*"
            if new_u
            else '',
        )
    )

    if mode == '+':
        res_ch_all.extend(new_ch)
        res_r_all.extend(new_r)
        res_u_all.extend(new_u)
    else:
        *(res_ch_all.remove(ch) for ch in new_ch),
        *(res_r_all.remove(r) for r in new_r),
        *(res_u_all.remove(u) for u in new_u),

    msg = f"📝 {delta_act} {deltas_msg}" if deltas_msg else delta_txt_skipped

    await say(ctx, content=msg)


# ~


## config prefix


config_g_s = config.with_slash_command(
    tj.slash_command_group('config', "Manage the bot's guild-specific settings")
)


prefix_sg_s = config_g_s.with_command(
    tj.slash_command_group('prefix', "Manages the bot's prefixes")
)


@config.with_message_command
@tj.as_message_command_group('config', 'con', 'settings', 'k', 'cfg', strict=True)
@with_message_command_group_template
async def config_g_m(_: tj.abc.MessageContext):
    """Manage the bot's guild-specific settings"""
    ...


@config_g_m.with_command
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
    await say(ctx, embed=embed)


### config prefix add


@prefix_sg_s.with_command
@tj.with_str_slash_option('prefix', "What prefix?")
@tj.as_slash_command('add', "Adds a new prefix of the bot for this guild")
# -
@prefix_sg_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('add', '+', 'a', 'new', 'create', 'n')
@check(perms=hkperms.ADMINISTRATOR)
async def prefix_add_(
    ctx: tj.abc.Context,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    """Adds a new prefix of the bot for this guild"""
    assert ctx.guild_id

    g_prefixes: list[str] = cfg[str(ctx.guild_id)].setdefault('prefixes', [])

    if prefix in g_prefixes + list(ctx.client.prefixes):
        await err_say(ctx, content=f"❗ Already defined this prefix")
        return

    cfg[str(ctx.guild_id)]['prefixes'].append(prefix)
    await say(
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
@check(perms=hkperms.ADMINISTRATOR)
async def prefix_remove_(
    ctx: tj.abc.Context,
    prefix: str,
    cfg: al.Injected[GuildConfig],
):
    """
    Removes an existing prefix of the bot for this guild
    """
    assert ctx.guild_id
    g_prefixes: list[str] = cfg[str(ctx.guild_id)].setdefault('prefixes', [])

    if prefix in ctx.client.prefixes:
        await err_say(ctx, content=f"❌ This prefix is global and cannot be removed")
        return

    elif prefix not in g_prefixes:
        await err_say(ctx, content=f"❗ No such prefix found")
        return

    g_prefixes.remove(prefix)
    await say(ctx, content=f"**`「／」ー`** Removed the prefix `{prefix}` for this guild")


## config nowplayingmsg


nowplayingmsg_sg_s = config_g_s.with_command(
    tj.slash_command_group('now-playing-msg', "Manages the bot's now playing messages")
)


@config_g_m.with_command
@tj.as_message_command_group(
    'nowplayingmsg', 'now-playing-msg', 'npmsg', 'np', strict=True
)
@with_message_command_group_template
async def nowplayingmsg_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's now playing messages"""
    ...


### config nowplayingmsg toggle


@nowplayingmsg_sg_s.with_command
@tj.as_slash_command(
    'toggle', "Toggles the now playing messages to be automatically sent or not"
)
# -
@nowplayingmsg_sg_m.with_command
@tj.as_message_command('toggle', 'tggl', 't')
@check(perms=hkperms.MANAGE_GUILD)
async def nowplayingmsg_toggle_(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    """Toggles the now playing messages to be automatically sent or not"""
    assert ctx.guild_id
    send_np_msg: bool = cfg[str(ctx.guild_id)].setdefault('send_nowplaying_msg', False)

    cfg[str(ctx.guild_id)]['send_nowplaying_msg'] = not send_np_msg
    msg = (
        "🔕 Not sending now playing messages from now on"
        if send_np_msg
        else "🔔 Sending now playing messages from now on"
    )
    await say(ctx, content=msg)


## config restricts


restrict_sg_s = config_g_s.with_command(
    tj.slash_command_group(
        'restrict', "Manages the bot's restricted channels, roles and members"
    )
)


@config_g_m.with_command
@tj.as_message_command_group('restrict', 'restr', 'rest', 'rst', 'r', strict=True)
@with_message_command_group_template
async def restrict_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's restricted channels, roles and members"""
    ...


### config restricts list


@restrict_sg_m.with_command
@tj.as_message_command('list', 'ls', 'l', '.', 'all', '/')
# -
@restrict_sg_s.with_command
@tj.as_slash_command('list', "Shows the current restricted channels, roles and members")
async def restrict_list_(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    """Shows the current restricted channels, roles and members"""

    assert ctx.guild_id
    g_cfg = cfg[str(ctx.guild_id)]

    res_ch: dict[str, t.Any] = g_cfg.get('restricted_ch', {})
    res_r: dict[str, t.Any] = g_cfg.get('restricted_r', {})
    res_u: dict[str, t.Any] = g_cfg.get('restricted_u', {})

    ch_wl = res_ch.get('wl_mode', 0)
    r_wl = res_r.get('wl_mode', 0)
    u_wl = res_u.get('wl_mode', 0)

    def empty_or(str_: str):
        return str_ or '```diff\n-Empty-\n```'

    embed = (
        hk.Embed(
            title=f"📝✅❌ All restricted channels, roles and members",
        )
        .add_field(
            f"Channels *({_c(ch_wl)})*",
            empty_or('\n'.join(f'{_e(ch_wl)} <#{r}>' for r in res_ch.get('all', []))),
        )
        .add_field(
            f"Roles *({_c(r_wl)})*",
            empty_or('\n'.join(f'{_e(r_wl)} <@&{r}>' for r in res_r.get('all', []))),
        )
        .add_field(
            f"Members *({_c(u_wl)})*",
            empty_or('\n'.join(f'{_e(u_wl)} <@{r}>' for r in res_u.get('all', []))),
        )
    )

    await say(ctx, embed=embed)


### config restricts add


@restrict_sg_m.with_command
@tj.with_multi_argument('mentionables', (tj.to_user, tj.to_role, tj.to_channel))
@tj.with_parser
@tj.as_message_command('add', 'a', '+')
async def restrict_add_m(
    ctx: tj.abc.MessageContext,
    mentionables: t.Collection[MentionableType],
    cfg: al.Injected[GuildConfig],
):
    await _restrict_add(ctx, mentionables, cfg)


@restrict_sg_s.with_command
@tj.with_mentionable_slash_option('mentionable', "Which channel/role/member ?")
@tj.as_slash_command(
    'add', "Adds new channels, roles or members to the restricted list"
)
async def restrict_add_s(
    ctx: tj.abc.SlashContext,
    mentionable: MentionableType,
    cfg: al.Injected[GuildConfig],
):
    await _restrict_add(ctx, [mentionable], cfg)


@check(perms=RESTRICTOR)
async def _restrict_add(
    ctx: tj.abc.Context,
    mentionables: t.Collection[MentionableType],
    cfg: GuildConfig,
):
    """Adds new channels, roles or members to the restricted list"""
    await restrict_list_edit(ctx, cfg, mentionables=mentionables, mode='+')


@restrict_sg_m.with_command
@tj.with_multi_argument('mentionables', (tj.to_user, tj.to_role, tj.to_channel))
@tj.with_parser
@tj.as_message_command('remove', 'rm', 'del', 'r', 'd', '-')
async def restrict_remove_m(
    ctx: tj.abc.MessageContext,
    mentionables: t.Collection[MentionableType],
    cfg: al.Injected[GuildConfig],
):
    await _restrict_remove(ctx, mentionables, cfg)


@restrict_sg_s.with_command
@tj.with_mentionable_slash_option('mentionable', "Which channel/role/member ?")
@tj.as_slash_command(
    'remove', "Removes existing channels, roles or members from the restricted list"
)
async def restrict_remove_s(
    ctx: tj.abc.SlashContext,
    mentionable: MentionableType,
    cfg: al.Injected[GuildConfig],
):
    await _restrict_remove(ctx, [mentionable], cfg)


### config restricts remove


@check(perms=RESTRICTOR)
async def _restrict_remove(
    ctx: tj.abc.Context,
    mentionables: t.Collection[MentionableType],
    cfg: GuildConfig,
):
    """Removes existing channels, roles or members from the restricted list"""
    await restrict_list_edit(ctx, cfg, mentionables=mentionables, mode='-')


### config restricts blacklist


@restrict_sg_m.with_command
@tj.with_argument('category', to_mentionable_category)
@tj.with_parser
@tj.as_message_command('blacklist', 'bl')
# -
@restrict_sg_s.with_command
@tj.with_str_slash_option(
    'category',
    "Which category?",
    choices=valid_mentionables,
)
@tj.as_slash_command('blacklist', "Sets a category's restriction mode to blacklisting")
@check(perms=RESTRICTOR)
async def restrict_blacklist_(
    ctx: tj.abc.Context, category: str, cfg: al.Injected[GuildConfig]
):
    """Sets a category's restriction mode to blacklisting"""
    await restrict_mode_set(ctx, cfg, category=category, mode=-1)


### config restricts blacklist


@restrict_sg_m.with_command
@tj.with_argument('category', to_mentionable_category)
@tj.with_parser
@tj.as_message_command('whitelist', 'wl')
# -
@restrict_sg_s.with_command
@tj.with_str_slash_option(
    'category',
    "Which category?",
    choices=valid_mentionables,
)
@tj.as_slash_command('whitelist', "Sets a category's restriction mode to whitelisting")
@check(perms=RESTRICTOR)
async def restrict_whitelist_(
    ctx: tj.abc.Context, category: str, cfg: al.Injected[GuildConfig]
):
    """Sets a category's restriction mode to whitelisting"""
    await restrict_mode_set(ctx, cfg, category=category, mode=1)


@restrict_sg_m.with_command
@tj.with_argument('wipe', tj.to_bool, default=True)
@tj.with_argument('category', to_mentionable_category)
@tj.with_parser
@tj.as_message_command('clear', 'clr')
# -
@restrict_sg_s.with_command
@tj.with_bool_slash_option(
    'wipe', "Also wipes the restricted list of that category? (If not given, Yes)"
)
@tj.with_str_slash_option(
    'category',
    "Which category?",
    choices=valid_mentionables,
)
@tj.as_slash_command('clear', "Clears a category's restriction mode")
@check(perms=RESTRICTOR)
async def restrict_clear_(
    ctx: tj.abc.Context, category: str, wipe: bool, cfg: al.Injected[GuildConfig]
):
    """Clears a category's restriction mode"""
    await restrict_mode_set(ctx, cfg, category=category, wipe=wipe)


## config restricts wipe


@restrict_sg_m.with_command
@tj.as_message_command('wipe', 'reset', 'wp')
# -
@restrict_sg_s.with_command
@tj.as_slash_command('wipe', "Wipes the restricted list of EVERY category")
@check(perms=RESTRICTOR, prompt=True)
async def restrict_wipe_(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    """Wipes the restricted list of EVERY category"""
    assert ctx.guild_id
    g_cfg = cfg[str(ctx.guild_id)]

    g_cfg['restricted_ch'] = {'all': [], 'wl_mode': 0}
    g_cfg['restricted_r'] = {'all': [], 'wl_mode': 0}
    g_cfg['restricted_u'] = {'all': [], 'wl_mode': 0}

    await say(
        ctx,
        content="📝🧹 Wiped all restricted channels, roles and members list and cleared the restriction modes",
    )


# -


loader = config.load_from_scope().make_loader()
