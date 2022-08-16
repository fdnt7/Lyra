import typing as t

import hikari as hk
import tanjun as tj
import alluka as al

from hikari.permissions import Permissions as hkperms

from ..lib.musicutils import init_component
from ..lib.dataimpl import LyraDBCollectionType
from ..lib.compose import Binds, with_author_permission_check, with_cmd_composer
from ..lib.extras import Panic, flatten, fmt_str, join_and, uniquify, split_preset
from ..lib.utils import (
    RESTRICTOR,
    MentionableType,
    PartialMentionableType,
    with_message_command_group_template,
    say,
    err_say,
)


config = init_component(__name__)


# ~

valid_mentionables: t.Final = {'Channels': 'ch', 'Roles': 'r', 'Members': 'u'}
inv_mentionables: t.Final = {v: k for k, v in valid_mentionables.items()}
BlacklistMode = t.Literal[-1, 0, 1]

all_mentionable_categories = split_preset(
    'channels|channel|chan|ch|c,roles|role|rle|r,users|user|members|member|usr|mbr|u|m'
)

with_dangerous_restricts_cmd_check = with_cmd_composer(Binds.CONFIRM, perms=RESTRICTOR)
with_admin_cmd_check = with_author_permission_check(hkperms.ADMINISTRATOR)
with_restricts_cmd_check = with_author_permission_check(RESTRICTOR)


def _c(b: BlacklistMode):
    return 'Whitelisted' if b == 1 else ('Blacklisted' if b == -1 else 'N/A')


def _e(b: BlacklistMode):
    return '✅' if b == 1 else ('❌' if b == -1 else '❔')


def to_mentionable_category(value: str) -> Panic[str]:
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


async def to_multi_mentionables(
    value: str, /, ctx: al.Injected[tj.abc.Context]
) -> Panic[frozenset[PartialMentionableType]]:
    _split = value.split()
    mentionables: t.Collection[PartialMentionableType] = set()

    for _m in _split:
        for conv in (tj.to_user, tj.to_role, tj.to_channel):
            try:
                mentionables.add(await conv(_m, ctx))
            except ValueError:
                continue
            else:
                break
        else:
            raise ValueError(f'Cannot convert mentionable {_m}')
    return frozenset(mentionables)


async def restrict_mode_set(
    ctx: tj.abc.Context,
    cfg: LyraDBCollectionType,
    /,
    *,
    category: str,
    mode: BlacklistMode = 0,
    wipe: bool = False,
):
    # pyright: reportUnknownMemberType=false
    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

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
    cfg.find_one_and_replace(flt, g_cfg)


async def restrict_list_edit(
    ctx: tj.abc.Context,
    cfg: LyraDBCollectionType,
    /,
    *,
    mentionables: t.Collection[MentionableType],
    mode: t.Literal['+', '-'],
):
    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

    res_ch = g_cfg.setdefault('restricted_ch', {})
    res_r = g_cfg.setdefault('restricted_r', {})
    res_u = g_cfg.setdefault('restricted_u', {})

    res_ch_all: list[str] = res_ch.setdefault('all', [])
    res_r_all: list[str] = res_r.setdefault('all', [])
    res_u_all: list[str] = res_u.setdefault('all', [])

    new_ch: list[str] = []
    new_r: list[str] = []
    new_u: list[str] = []

    for u in uniquify(mentionables):
        u_in_list = (u_id := str(u.id)) in res_ch_all + res_r_all + res_u_all
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
    cfg.find_one_and_replace(flt, g_cfg)


## config prefix


config_g_s = config.with_command(
    tj.slash_command_group('config', "Manage the bot's guild-specific settings")
)


prefix_sg_s = config_g_s.with_command(
    tj.slash_command_group('prefix', "Manages the bot's prefixes")
)


@tj.as_message_command_group(
    'config',
    'con',
    'cfg',
    'settings',
    'k',
    'preferences',
    'preference',
    'prefs',
    'pref',
    'prf',
    strict=True,
)
@with_message_command_group_template
async def config_g_m(_: tj.abc.MessageContext):
    """Manage the bot's guild-specific settings"""
    ...


@config_g_m.with_command
@tj.as_message_command_group('prefix', 'pfx', '/', strict=True)
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
async def prefix_list_(
    ctx: tj.abc.Context, cfg: al.Injected[LyraDBCollectionType]
) -> None:
    """Lists all usable prefixes of the bot"""

    assert ctx.guild_id
    g_cfg = cfg.find_one({'id': str(ctx.guild_id)})
    assert g_cfg

    g_prefixes: list[str] = g_cfg.setdefault('prefixes', [])

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
@with_admin_cmd_check
@tj.with_str_slash_option('prefix', "What prefix?")
@tj.as_slash_command('add', "Adds a new prefix of the bot for this guild")
# -
@prefix_sg_m.with_command
@with_admin_cmd_check
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('add', '+', 'a', 'new', 'create', 'n')
async def prefix_add_(
    ctx: tj.abc.Context,
    prefix: str,
    cfg: al.Injected[LyraDBCollectionType],
):
    """Adds a new prefix of the bot for this guild"""

    # pyright: reportUnknownMemberType=false
    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

    g_prefixes: list[str] = g_cfg.setdefault('prefixes', [])

    if prefix in g_prefixes + list(ctx.client.prefixes):
        await err_say(ctx, content=f"❗ Already defined this prefix")
        return

    g_prefixes.append(prefix)
    await say(
        ctx, content=f"**`「／」+`** Added `{prefix}` as a new prefix for this guild"
    )
    cfg.find_one_and_replace(flt, g_cfg)


### config prefix remove


@prefix_sg_s.with_command
@with_admin_cmd_check
@tj.with_str_slash_option('prefix', "Which prefix?")
@tj.as_slash_command('remove', "Removes an existing prefix of the bot for this guild")
#
@prefix_sg_m.with_command
@with_admin_cmd_check
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('remove', '-', 'rem', 'r', 'rm', 'd', 'del', 'delete')
async def prefix_remove_(
    ctx: tj.abc.Context,
    prefix: str,
    cfg: al.Injected[LyraDBCollectionType],
):
    """Removes an existing prefix of the bot for this guild"""

    # pyright: reportUnknownMemberType=false
    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

    g_prefixes: list[str] = g_cfg.setdefault('prefixes', [])

    if prefix in ctx.client.prefixes:
        await err_say(ctx, content=f"❌ This prefix is global and cannot be removed")
        return

    elif prefix not in g_prefixes:
        await err_say(ctx, content=f"❗ No such prefix found")
        return

    g_prefixes.remove(prefix)
    await say(ctx, content=f"**`「／」ー`** Removed the prefix `{prefix}` for this guild")
    cfg.find_one_and_replace(flt, g_cfg)


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
@with_author_permission_check(hkperms.MANAGE_GUILD)
@tj.as_slash_command(
    'toggle', "Toggles the now playing messages to be automatically sent or not"
)
#
@nowplayingmsg_sg_m.with_command
@with_author_permission_check(hkperms.MANAGE_GUILD)
@tj.as_message_command('toggle', 'tggl', 't')
async def nowplayingmsg_toggle_(
    ctx: tj.abc.Context, cfg: al.Injected[LyraDBCollectionType]
):
    """Toggles the now playing messages to be automatically sent or not"""

    # pyright: reportUnknownMemberType=false
    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

    send_np_msg: bool = g_cfg.setdefault('send_nowplaying_msg', False)

    g_cfg['send_nowplaying_msg'] = not send_np_msg
    msg = (
        "🔕 Not sending now playing messages from now on"
        if send_np_msg
        else "🔔 Sending now playing messages from now on"
    )
    await say(ctx, content=msg)
    cfg.find_one_and_replace(flt, g_cfg)


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
async def restrict_list_(ctx: tj.abc.Context, cfg: al.Injected[LyraDBCollectionType]):
    """Shows the current restricted channels, roles and members"""

    assert ctx.guild_id
    g_cfg = cfg.find_one({'id': str(ctx.guild_id)})
    assert g_cfg

    res_ch: dict[str, t.Any] = g_cfg.get('restricted_ch', {})
    res_r: dict[str, t.Any] = g_cfg.get('restricted_r', {})
    res_u: dict[str, t.Any] = g_cfg.get('restricted_u', {})

    ch_wl: BlacklistMode = res_ch.get('wl_mode', 0)
    r_wl: BlacklistMode = res_r.get('wl_mode', 0)
    u_wl: BlacklistMode = res_u.get('wl_mode', 0)

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
@with_author_permission_check(RESTRICTOR)
@tj.with_multi_argument('mentionables', (tj.to_user, tj.to_role, tj.to_channel))
@tj.with_parser
@tj.as_message_command('add', 'a', '+')
#
@restrict_sg_s.with_command
@with_author_permission_check(RESTRICTOR)
@tj.with_str_slash_option(
    'mentionables',
    "Which channel/role/member ?",
    converters=to_multi_mentionables,
)
@tj.as_slash_command(
    'add', "Adds new channels, roles or members to the restricted list"
)
async def restrict_add_(
    ctx: tj.abc.MessageContext,
    mentionables: t.Collection[MentionableType],
    cfg: al.Injected[LyraDBCollectionType],
):
    """Adds new channels, roles or members to the restricted list"""
    await restrict_list_edit(ctx, cfg, mentionables=mentionables, mode='+')


### config restricts remove


@restrict_sg_m.with_command
@with_restricts_cmd_check
@tj.with_multi_argument('mentionables', (tj.to_user, tj.to_role, tj.to_channel))
@tj.with_parser
@tj.as_message_command('remove', 'rm', 'del', 'r', 'd', '-')
#
@restrict_sg_s.with_command
@with_restricts_cmd_check
@tj.with_str_slash_option(
    'mentionables',
    "Which channel/role/member ?",
    converters=to_multi_mentionables,
)
@tj.as_slash_command(
    'remove', "Removes existing channels, roles or members from the restricted list"
)
async def restrict_remove_(
    ctx: tj.abc.MessageContext,
    mentionables: t.Collection[MentionableType],
    cfg: al.Injected[LyraDBCollectionType],
):
    """Removes existing channels, roles or members from the restricted list"""

    await restrict_list_edit(ctx, cfg, mentionables=mentionables, mode='-')


### config restricts blacklist


@restrict_sg_m.with_command
@with_restricts_cmd_check
@tj.with_argument('category', to_mentionable_category)
@tj.with_parser
@tj.as_message_command('blacklist', 'bl')
# -
@restrict_sg_s.with_command
@with_restricts_cmd_check
@tj.with_str_slash_option(
    'category',
    "Which category?",
    choices=valid_mentionables,
)
@tj.as_slash_command('blacklist', "Sets a category's restriction mode to blacklisting")
async def restrict_blacklist_(
    ctx: tj.abc.Context, category: str, cfg: al.Injected[LyraDBCollectionType]
):
    """Sets a category's restriction mode to blacklisting"""

    await restrict_mode_set(ctx, cfg, category=category, mode=-1)


### config restricts blacklist


@restrict_sg_m.with_command
@with_restricts_cmd_check
@tj.with_argument('category', to_mentionable_category)
@tj.with_parser
@tj.as_message_command('whitelist', 'wl')
# -
@restrict_sg_s.with_command
@with_restricts_cmd_check
@tj.with_str_slash_option(
    'category',
    "Which category?",
    choices=valid_mentionables,
)
@tj.as_slash_command('whitelist', "Sets a category's restriction mode to whitelisting")
async def restrict_whitelist_(
    ctx: tj.abc.Context, category: str, cfg: al.Injected[LyraDBCollectionType]
):
    """Sets a category's restriction mode to whitelisting"""

    await restrict_mode_set(ctx, cfg, category=category, mode=1)


@restrict_sg_m.with_command
@with_restricts_cmd_check
@tj.with_argument('wipe', tj.to_bool, default=True)
@tj.with_argument('category', to_mentionable_category)
@tj.with_parser
@tj.as_message_command('clear', 'clr')
# -
@restrict_sg_s.with_command
@with_restricts_cmd_check
@tj.with_bool_slash_option(
    'wipe', "Also wipes the restricted list of that category? (If not given, Yes)"
)
@tj.with_str_slash_option(
    'category',
    "Which category?",
    choices=valid_mentionables,
)
@tj.as_slash_command('clear', "Clears a category's restriction mode")
async def restrict_clear_(
    ctx: tj.abc.Context,
    category: str,
    wipe: bool,
    cfg: al.Injected[LyraDBCollectionType],
):
    """Clears a category's restriction mode"""

    await restrict_mode_set(ctx, cfg, category=category, wipe=wipe)


## config restricts wipe


@restrict_sg_m.with_command
@with_dangerous_restricts_cmd_check
@tj.as_message_command('wipe', 'reset', 'wp')
# -
@restrict_sg_s.with_command
@with_dangerous_restricts_cmd_check
@tj.as_slash_command('wipe', "Wipes the restricted list of EVERY category")
async def restrict_wipe_(ctx: tj.abc.Context, cfg: al.Injected[LyraDBCollectionType]):
    """Wipes the restricted list of EVERY category"""

    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

    g_cfg['restricted_ch'] = {'all': [], 'wl_mode': 0}
    g_cfg['restricted_r'] = {'all': [], 'wl_mode': 0}
    g_cfg['restricted_u'] = {'all': [], 'wl_mode': 0}

    await say(
        ctx,
        content="📝🧹 Wiped all restricted channels, roles and members list and cleared the restriction modes",
    )
    cfg.find_one_and_replace(flt, g_cfg)


# -


loader = config.load_from_scope().make_loader()
