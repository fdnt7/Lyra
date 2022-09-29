import typing as t

import hikari as hk
import tanjun as tj
import alluka as al
import tanjun.annotations as ja

from hikari.permissions import Permissions as hkperms

from ..lib.cmd.ids import CommandIdentifier as C
from ..lib.cmd.compose import (
    Binds,
    with_author_permission_check,
    with_cmd_composer,
    with_identifier,
)
from ..lib.musicutils import __init_component__
from ..lib.dataimpl import LyraDBCollectionType
from ..lib.extras import (
    Panic,
    flatten,
    fmt_str,
    join_and,
    map_in_place,
    uniquify,
    split_preset,
)
from ..lib.utils import (
    RESTRICTOR,
    MentionableType,
    PartialMentionableType,
    with_annotated_args_wrapped,
    with_message_command_group_template,
    say,
    err_say,
)
from ..lib.utils.fmt import ANSI_BLOCK, Fore, cl


config = __init_component__(__name__)


# ~


valid_mentionables: t.Final = {'Channels': 'ch', 'Roles': 'r', 'Members': 'u'}
inv_mentionables: t.Final = {v: k for k, v in valid_mentionables.items()}
BlacklistMode = t.Literal[-1, 0, 1]
CategoryType = t.Literal['ch', 'r', 'u']

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
    category: str,  # TODO: change this to `CategoryType` once 3.11 is out
    mode: BlacklistMode = 0,
    wipe: bool = False,
):
    assert ctx.guild_id
    flt = {'id': str(ctx.guild_id)}

    g_cfg = cfg.find_one(flt)
    assert g_cfg

    cat_name = inv_mentionables[category]
    mode_name = _c(mode)

    res: dict[str, t.Any] = g_cfg.setdefault('restricted_%s' % category, {})

    if wipe:
        res.setdefault('all', []).clear()
        wipe_msg = " and cleared all %s(s) from the restricted list" % cat_name.lower()
    else:
        wipe_msg = ""

    if res.get('wl_mode', 0) == mode:
        await say(
            ctx,
            hidden=True,
            content=f"""{'🧹' if wipe else '❕'} Already set {cat_name.lower()} restricted mode to *{mode_name}*{wipe_msg.replace('and', 'but also', 1)}""",
        )
        return
    res['wl_mode'] = mode

    if mode == 0:
        msg = f"""🔐{_e(mode)}{'🧹' if wipe else ''} Cleared {cat_name.lower()} restriction mode{wipe_msg}"""
    else:
        msg = f"🔐{_e(mode)} Set *{cat_name.lower()}* restriction mode to **`{mode_name}`**"

    await say(ctx, content=msg)
    cfg.find_one_and_replace(flt, g_cfg)


async def restrict_list_edit(
    ctx: tj.abc.Context,
    cfg: LyraDBCollectionType,
    /,
    *,
    mentionables: t.Collection[PartialMentionableType],
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
        "❕🔐 No new restricted channels, roles or members were added as they've already been assigned"
        if mode == '+'
        else "❕🔐 No existing restricted channels, roles or members were removed as they weren't in the list"
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
        map_in_place(lambda ch: res_ch_all.remove(ch), new_ch)
        map_in_place(lambda r: res_r_all.remove(r), new_r)
        map_in_place(lambda u: res_u_all.remove(u), new_u)

    msg = f"🔐 {delta_act} {deltas_msg}" if deltas_msg else delta_txt_skipped

    await say(ctx, content=msg)
    cfg.find_one_and_replace(flt, g_cfg)


# /config


config_g_s = with_identifier(C.CONFIG)(
    tj.slash_command_group('config', "Manage the bot's guild-specific settings")
)


@with_identifier(C.CONFIG)
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


## /config prefix


@with_identifier(C.CONFIG_PREFIX)
# -
@config_g_m.as_sub_group('prefix', 'pfx', '/')
@with_message_command_group_template
async def prefix_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's prefixes"""
    ...


prefix_sg_s = with_identifier(C.CONFIG_PREFIX)(
    config_g_s.with_command(
        (tj.slash_command_group('prefix', "Manages the bot's prefixes"))
    )
)


### /config prefix list


@with_identifier(C.CONFIG_PREFIX_LIST)
# -
@prefix_sg_m.as_sub_command('list', 'l', '.')
@prefix_sg_s.as_sub_command('list', "Lists all usable prefixes of the bot")
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
        '\n'.join('`%s`' % prf for prf in g_prefixes)
        or ANSI_BLOCK % cl("Empty", fore=Fore.D),
        inline=True,
    )
    await say(ctx, embed=embed)


### /config prefix add


@with_annotated_args_wrapped
@with_admin_cmd_check(C.CONFIG_PREFIX_ADD)
# -
@prefix_sg_m.as_sub_command('add', '+', 'a', 'new', 'create', 'n')
@prefix_sg_s.as_sub_command('add', "Adds a new prefix of the bot for this guild")
async def prefix_add_(
    ctx: tj.abc.Context,
    cfg: al.Injected[LyraDBCollectionType],
    prefix: t.Annotated[ja.Str, "What prefix?"],
):
    """Adds a new prefix of the bot for this guild"""

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


### /config prefix remove


@with_annotated_args_wrapped
@with_admin_cmd_check(C.CONFIG_PREFIX_REMOVE)
# -
@prefix_sg_m.as_sub_command('remove', '-', 'rem', 'r', 'rm', 'd', 'del', 'delete')
@prefix_sg_s.as_sub_command(
    'remove', "Removes an existing prefix of the bot for this guild"
)
async def prefix_remove_(
    ctx: tj.abc.Context,
    cfg: al.Injected[LyraDBCollectionType],
    prefix: t.Annotated[ja.Str, "Which prefix?"],
):
    """Removes an existing prefix of the bot for this guild"""

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


## /config nowplayingmsg


@with_identifier(C.CONFIG_NOWPLAYINGMSG)
# -
@config_g_m.with_command
@tj.as_message_command_group(
    'nowplayingmsg', 'now-playing-msg', 'npmsg', 'np', strict=True
)
@with_message_command_group_template
async def nowplayingmsg_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's now playing messages"""
    ...


nowplayingmsg_sg_s = with_identifier(C.CONFIG_NOWPLAYINGMSG)(
    config_g_s.with_command(
        tj.slash_command_group(
            'now-playing-msg', "Manages the bot's now playing messages"
        )
    )
)


### /config nowplayingmsg toggle


@with_author_permission_check(hkperms.MANAGE_GUILD)(C.CONFIG_NOWPLAYINGMSG_TOGGLE)
# -
@nowplayingmsg_sg_m.as_sub_command('toggle', 'tggl', 't')
@nowplayingmsg_sg_s.as_sub_command(
    'toggle', "Toggles the now playing messages to be automatically sent or not"
)
async def nowplayingmsg_toggle_(
    ctx: tj.abc.Context, cfg: al.Injected[LyraDBCollectionType]
):
    """Toggles the now playing messages to be automatically sent or not"""

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


## /config restrict


@with_identifier(C.CONFIG_RESTRICT)
# -
@config_g_m.with_command
@tj.as_message_command_group('restrict', 'restr', 'rest', 'rst', 'r', strict=True)
@with_message_command_group_template
async def restrict_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's restricted channels, roles and members"""
    ...


restrict_sg_s = with_identifier(C.CONFIG_RESTRICT)(
    config_g_s.with_command(
        tj.slash_command_group(
            'restrict', "Manages the bot's restricted channels, roles and members"
        )
    )
)


### /config restrict list


@with_identifier(C.CONFIG_RESTRICT_LIST)
# -
@restrict_sg_m.as_sub_command('list', 'ls', 'l', '.', 'all', '/')
@restrict_sg_s.as_sub_command(
    'list', "Shows the current restricted channels, roles and members"
)
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
        return str_ or ANSI_BLOCK % cl("Empty", fore=Fore.D)

    embed = (
        hk.Embed(
            title=f"🔐✅❌ All restricted channels, roles and members",
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


### /config restrict add


@with_annotated_args_wrapped
@with_restricts_cmd_check(C.CONFIG_RESTRICT_ADD)
# -
@restrict_sg_m.as_sub_command('add', 'a', '+')
@restrict_sg_s.as_sub_command(
    'add', "Adds new channels, roles or members to the restricted list"
)
# TODO: Remove tyoe casting when tanjun relaxed converter func sig
async def restrict_add_(
    ctx: tj.abc.MessageContext,
    cfg: al.Injected[LyraDBCollectionType],
    mentionables: t.Annotated[
        ja.Greedy[
            ja.Converted[
                t.cast(
                    t.Callable[[str], frozenset[MentionableType]],
                    to_multi_mentionables,
                )
            ]
        ],
        "Which channel/role/member?",
    ],
):
    """Adds new channels, roles or members to the restricted list"""

    await restrict_list_edit(
        ctx,
        cfg,
        mentionables=mentionables,
        mode='+',
    )


### /config restrict remove


@with_annotated_args_wrapped
@with_restricts_cmd_check(C.CONFIG_RESTRICT_REMOVE)
# -
@restrict_sg_m.as_sub_command('remove', 'rm', 'del', 'r', 'd', '-')
@restrict_sg_s.as_sub_command(
    'remove', "Removes existing channels, roles or members from the restricted list"
)
# TODO: Remove type casting when tanjun relaxed converter func sig
async def restrict_remove_(
    ctx: tj.abc.MessageContext,
    cfg: al.Injected[LyraDBCollectionType],
    mentionables: t.Annotated[
        ja.Greedy[
            ja.Converted[
                t.cast(
                    t.Callable[[str], frozenset[MentionableType]],
                    to_multi_mentionables,
                )
            ]
        ],
        "Which channel/role/member?",
    ],
):
    """Removes existing channels, roles or members from the restricted list"""

    await restrict_list_edit(
        ctx,
        cfg,
        mentionables=mentionables,
        mode='-',
    )


### /config restrict blacklist


@with_annotated_args_wrapped
@with_restricts_cmd_check(C.CONFIG_RESTRICT_BLACKLIST)
# -
@restrict_sg_m.as_sub_command('blacklist', 'bl')
@restrict_sg_s.as_sub_command(
    'blacklist', "Sets a category's restriction mode to blacklisting"
)
async def restrict_blacklist_(
    ctx: tj.abc.Context,
    cfg: al.Injected[LyraDBCollectionType],
    category: t.Annotated[
        ja.Converted[to_mentionable_category],
        "Which category?",
        ja.Choices(valid_mentionables),
    ],
):
    """Sets a category's restriction mode to blacklisting"""

    await restrict_mode_set(ctx, cfg, category=category, mode=-1)


### /config restrict whitelist


@with_annotated_args_wrapped
@with_restricts_cmd_check(C.CONFIG_RESTRICT_WHITELIST)
# -
@restrict_sg_m.as_sub_command('whitelist', 'wl')
@restrict_sg_s.as_sub_command(
    'whitelist', "Sets a category's restriction mode to whitelisting"
)
async def restrict_whitelist_(
    ctx: tj.abc.Context,
    cfg: al.Injected[LyraDBCollectionType],
    category: t.Annotated[
        ja.Converted[to_mentionable_category],
        "Which category?",
        ja.Choices(valid_mentionables),
    ],
):
    """Sets a category's restriction mode to whitelisting"""

    await restrict_mode_set(ctx, cfg, category=category, mode=1)


### /config restrict clear


@with_annotated_args_wrapped
@with_restricts_cmd_check(C.CONFIG_RESTRICT_CLEAR)
# -
@restrict_sg_m.as_sub_command('clear', 'clr')
@restrict_sg_s.as_sub_command('clear', "Clears a category's restriction mode")
async def restrict_clear_(
    ctx: tj.abc.Context,
    cfg: al.Injected[LyraDBCollectionType],
    category: t.Annotated[
        ja.Converted[to_mentionable_category],
        "Which category?",
        ja.Choices(valid_mentionables),
    ],
    wipe: t.Annotated[
        ja.Bool,
        "Also wipes the restricted list of that category? (If not given, Yes)",
        ja.Flag(aliases=('-w',)),
    ] = True,
):
    """Clears a category's restriction mode"""

    await restrict_mode_set(ctx, cfg, category=category, wipe=wipe)


### /config restrict wipe


@with_dangerous_restricts_cmd_check(C.CONFIG_RESTRICT_WIPE)
# -
@restrict_sg_m.as_sub_command('wipe', 'reset', 'wp')
@restrict_sg_s.as_sub_command('wipe', "Wipes the restricted list of EVERY category")
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
        content="🔐🧹 Wiped all restricted channels, roles and members list and cleared the restriction modes",
    )
    cfg.find_one_and_replace(flt, g_cfg)


# -


loader = config.load_from_scope().make_loader()
