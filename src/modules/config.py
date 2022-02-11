from src.lib.utils import *
from src.lib.music import music_h
from src.lib.checks import Checks, check


config = tj.Component(name='Config').add_check(guild_c).set_hooks(music_h)


# prefix


prefix_g_s = config.with_slash_command(
    tj.slash_command_group('prefix', "Manages the bot's prefixes")
)


@config.with_message_command
@tj.as_message_command_group('prefix', 'pref', 'prf', '/', strict=True)
@with_message_command_group_template
async def prefix_g_m(ctx: tj.abc.MessageContext):
    """Manages the bot's prefixes"""
    ...


## prefix list


@prefix_g_s.with_command
@tj.as_slash_command('list', "Lists all usable of the bot")
async def prefix_list_s(
    ctx: tj.abc.SlashContext, gsts: GuildSettings = tj.injected(type=GuildSettings)
):
    await prefix_list_(ctx, gsts=gsts)


@prefix_g_m.with_command
@tj.as_message_command('list', 'l', '.')
async def prefix_list_m(
    ctx: tj.abc.MessageContext, gsts: GuildSettings = tj.injected(type=GuildSettings)
):
    """
    Lists all usable prefixes of the bot
    """
    await prefix_list_(ctx, gsts=gsts)


async def prefix_list_(ctx: tj.abc.Context, /, *, gsts: GuildSettings) -> None:
    """Lists all usable prefixes of the bot"""
    assert ctx.guild_id

    g_prefixes: list[str] = gsts.setdefault(str(ctx.guild_id), {}).get('prefixes', [])

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


## prefix add


@prefix_g_s.with_command
@tj.with_str_slash_option('prefix', "What prefix?")
@tj.as_slash_command('add', "Adds a new prefix of the bot for this guild")
async def prefix_add_s(
    ctx: tj.abc.SlashContext,
    prefix: str,
    gsts: GuildSettings = tj.injected(type=GuildSettings),
):
    await prefix_add_(ctx, prefix, gsts=gsts)


@prefix_g_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('add', '+', 'a', 'new', 'create', 'n')
async def prefix_add_m(
    ctx: tj.abc.MessageContext,
    prefix: str,
    gsts: GuildSettings = tj.injected(type=GuildSettings),
):
    """
    Adds a new prefix of the bot for this guild
    """
    await prefix_add_(ctx, prefix, gsts=gsts)


@check(perms=hkperms.ADMINISTRATOR)
async def prefix_add_(
    ctx: tj.abc.Context, prefix: str, /, *, gsts: GuildSettings
) -> None:
    """Adds a new prefix of the bot for this guild"""

    g_prefixes: list[str] = gsts.setdefault(str(ctx.guild_id), {}).get('prefixes', [])

    if prefix in g_prefixes + list(ctx.client.prefixes):
        await err_reply(ctx, content=f"❗ Already defined this prefix")
        return

    gsts[str(ctx.guild_id)]['prefixes'].append(prefix)
    await reply(
        ctx, content=f"**`「／」+`** Added `{prefix}` as a new prefix for this guild"
    )


## prefix remove


@prefix_g_s.with_command
@tj.with_str_slash_option('prefix', "Which prefix?")
@tj.as_slash_command('remove', "Removes an existing prefix of the bot for this guild")
async def prefix_remove_s(
    ctx: tj.abc.SlashContext,
    prefix: str,
    gsts: GuildSettings = tj.injected(type=GuildSettings),
):
    await prefix_remove_(ctx, prefix, gsts=gsts)


@prefix_g_m.with_command
@tj.with_argument('prefix')
@tj.with_parser
@tj.as_message_command('remove', '-', 'rem', 'r', 'rm', 'd', 'del', 'delete')
async def prefix_remove_m(
    ctx: tj.abc.MessageContext,
    prefix: str,
    gsts: GuildSettings = tj.injected(type=GuildSettings),
):
    """
    Removes an existing prefix of the bot for this guild
    """
    await prefix_remove_(ctx, prefix, gsts=gsts)


@check(perms=hkperms.ADMINISTRATOR)
async def prefix_remove_(
    ctx: tj.abc.Context, prefix: str, /, *, gsts: GuildSettings
) -> None:
    """Removes an existing prefix of the bot for this guild"""
    g_prefixes: list[str] = gsts.setdefault(str(ctx.guild_id), {}).get('prefixes', [])

    if prefix in ctx.client.prefixes:
        await err_reply(ctx, content=f"❌ This prefix is global and cannot be removed")
        return

    elif prefix not in g_prefixes:
        await err_reply(ctx, content=f"❗ No such prefix found")
        return

    g_prefixes.remove(prefix)
    await reply(ctx, content=f"**`「／」ー`** Removed the prefix `{prefix}` for this guild")


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(config.copy())
