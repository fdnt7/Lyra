import typing as t
import logging
import pathlib as pl

import hikari as hk
import tanjun as tj
import tanjun.annotations as ja

from ..lib.extras import lgfmt
from ..lib.utils import (
    say,
    err_say,
    with_annotated_args_wrapped,
    with_message_command_group_template,
)
from ..lib.cmd import CommandIdentifier as C, as_developer_check, with_identifier
from ..lib.music import __init_component__


debug = (
    __init_component__(
        __name__, guild_check=False, music_hook=False, other_checks=as_developer_check
    )
    .set_default_app_command_permissions(hk.Permissions.ADMINISTRATOR)
    .set_dms_enabled_for_app_cmds(True)
)


# ~


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


modules = {p.stem: p for p in pl.Path('.').glob('./src/modules/*.py')}
modules_tup = (*modules,)


# /debug


@with_identifier(C.DEBUG)
# -
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


debug_g_s = with_identifier(C.DEBUG)(
    tj.slash_command_group('debug', "For debugging purposes only")
)


## /debug module


@with_identifier(C.DEBUG_MODULE)
# -
@debug_g_m.as_sub_group(
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


module_sg_s = with_identifier(C.DEBUG_MODULE)(
    debug_g_s.with_command(
        tj.slash_command_group('module', "Manages the bot's modules")
    )
)


### /debug module reload


@with_annotated_args_wrapped
@with_identifier(C.DEBUG_MODULE_RELOAD)
# -
@module_sg_m.as_sub_command('reload', 'rl')
@module_sg_s.as_sub_command('reload', "Reloads a module")
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


@with_annotated_args_wrapped
@with_identifier(C.DEBUG_MODULE_UNLOAD)
# -
@module_sg_m.as_sub_command('unload', 'ul')
@module_sg_s.as_sub_command('unload', "Unloads a module")
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


@with_annotated_args_wrapped
@with_identifier(C.DEBUG_MODULE_LOAD)
# -
@module_sg_m.as_sub_command('load', 'lo')
@module_sg_s.as_sub_command('load', "Loads a module")
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


@with_identifier(C.DEBUG_COMMAND)
# -
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


command_sg_s = with_identifier(C.DEBUG_COMMAND)(
    debug_g_s.with_command(
        tj.slash_command_group('command', "Manages the bot's commands")
    )
)


### /debug command delete-all


@with_identifier(C.DEBUG_COMMAND_DELETEALL)
# -
@command_sg_m.as_sub_command('delete-all', 'deleteall', 'delall', 'wipe', 'wp')
@command_sg_s.as_sub_command('delete-all', "Deletes all application commands")
async def delete_all_app_commands(ctx: tj.abc.Context):
    """Deletes all global commands"""

    await say(ctx, content="⏳⚙️🗑️ Deleting all app commands...")
    await ctx.client.clear_application_commands()
    await say(ctx, follow_up=True, content="⚙️🗑️ Done")


# -


loader = debug.load_from_scope().make_loader()
