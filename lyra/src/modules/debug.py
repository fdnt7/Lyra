import typing as t
import logging
import pathlib as pl

import hikari as hk
import tanjun as tj
import alluka as al
import tanjun.annotations as ja

from hikari.permissions import Permissions as hkperms

from ..lib.flags import as_developer_check
from ..lib.musicutils import __init_component__
from ..lib.extras import lgfmt
from ..lib.utils import (
    say,
    err_say,
    with_annotated_args,
    with_message_command_group_template,
)


debug = (
    __init_component__(
        __name__, guild_check=False, music_hook=False, other_checks={as_developer_check}
    )
    .set_default_app_command_permissions(hkperms.ADMINISTRATOR)
    .set_dms_enabled_for_app_cmds(True)
)


# ~


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


modules = {p.stem: p for p in pl.Path('.').glob('./src/modules/*.py')}
modules_tup = (*modules,)


# /debug


debug_g_s = tj.slash_command_group('debug', "For debugging purposes only")


@tj.as_message_command_group(
    'debug',
    'dbg',
    'bot',
    'lyra',
    strict=True,
)
@with_message_command_group_template
async def debug_g_m(_: tj.abc.MessageContext):
    """For debugging purposes only"""
    ...


## /debug module


module_sg_s = debug_g_s.with_command(
    tj.slash_command_group('module', "Manages the bot's modules")
)


@debug_g_m.with_command
@tj.as_message_command_group(
    'module',
    'modules',
    'm',
    'mod',
    'mods',
    strict=True,
)
@with_message_command_group_template
async def module_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's modules"""
    ...


### /debug module reload


@with_annotated_args
# -
@module_sg_s.with_command
@tj.as_slash_command('reload', "Reloads a module")
@module_sg_m.with_command
@tj.as_message_command('reload', 'rl')
async def reload_module(
    ctx: tj.abc.Context,
    module: t.Annotated[ja.Str, "Which module?", ja.Choices(modules_tup)],
):
    """Reload a module in tanjun"""

    mod = modules[module]
    try:
        ctx.client.reload_modules(mod)
    except ValueError:
        ctx.client.load_modules(mod)

    await say(ctx, content=f"⚙️♻️ Reloaded `{mod.stem}`")


### /debug module unload


@with_annotated_args
# -
@module_sg_s.with_command
@tj.as_slash_command('unload', "Unloads a module")
@module_sg_m.with_command
@tj.as_message_command('unload', 'ul')
async def unload_module(
    ctx: tj.abc.Context,
    module: t.Annotated[ja.Str, "Which module?", ja.Choices(modules_tup)],
):
    """Unload a module in tanjun"""

    mod = modules[module]
    try:
        ctx.client.unload_modules(mod)
    except ValueError:
        await err_say(ctx, content=f"❗ Couldn't unload `{mod.stem}`")
        return

    await say(ctx, content=f"⚙️📤 Unloaded `{mod.stem}`")


### /debug module load


@with_annotated_args
# -
@module_sg_s.with_command
@tj.as_slash_command('load', "Loads a module")
@module_sg_m.with_command
@tj.as_message_command('load', 'lo')
async def load_module(
    ctx: tj.abc.Context,
    module: t.Annotated[ja.Str, "Which module?", ja.Choices(modules_tup)],
):
    """Load a module in tanjun"""

    mod = modules[module]
    try:
        ctx.client.load_modules(mod)
    except ValueError:
        await err_say(ctx, content=f"❗ Couldn't load `{mod.stem}`")
        return

    await say(ctx, content=f"⚙️📥 Loaded `{mod.stem}`")


## /debug command


command_sg_s = debug_g_s.with_command(
    tj.slash_command_group('command', "Manages the bot's commands")
)


@debug_g_m.with_command
@tj.as_message_command_group(
    'commands',
    'command',
    'cmds',
    'cmd',
    strict=True,
)
@with_message_command_group_template
async def command_sg_m(_: tj.abc.MessageContext):
    """Manages the bot's commands"""
    ...


### /debug command delete-all


@command_sg_s.with_command
@tj.as_slash_command('delete-all', "Deletes all application commands")
@command_sg_m.with_command
@tj.as_message_command('delete-all', 'deleteall', 'delall', 'wipe', 'wp')
async def delete_all_app_commands(ctx: tj.abc.Context, bot: al.Injected[hk.GatewayBot]):
    """Deletes all global commands"""

    me = bot.get_me()
    assert me
    cmds = await bot.rest.fetch_application_commands(me.id)
    L = len(cmds)
    await say(ctx, content="⏳⚙️🗑️ Deleting all app commands...")
    for i, cmd in enumerate(cmds, 1):
        await cmd.delete()
        logger.debug(f"Deleting global application commands {i}/{L} ({cmd.name})")
    await say(ctx, follow_up=True, content="⚙️🗑️ Done")


# -


loader = debug.load_from_scope().make_loader()
