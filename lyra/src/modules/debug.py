import typing as t
import logging
import pathlib as pl

import hikari as hk
import tanjun as tj
import alluka as al
import tanjun.annotations as ja

import src.lib.consts as c

from ..lib.musicutils import init_component
from ..lib.extras import lgfmt
from ..lib.utils import say, err_say, with_annotated_args


debug = init_component(__name__, guild_check=False, music_hook=False)


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


modules = {p.stem: p for p in pl.Path('.').glob('./src/modules/*.py')}
modules_tup = tuple(modules)


@with_annotated_args
@tj.as_slash_command('reload', "Reloads a module.")
#
@tj.as_message_command('reload', 'rl')
async def reload_module(
    ctx: tj.abc.Context,
    module: t.Annotated[ja.Str, "Which module?", ja.Choices(modules_tup)],
):
    """Reload a module in tanjun"""

    if ctx.author.id not in c.__developers__:
        await err_say(ctx, content="🚫⚙️ Reserved for bot's developers only")
        return
    mod = modules[module]
    try:
        ctx.client.reload_modules(mod)
    except ValueError:
        ctx.client.load_modules(mod)

    await say(ctx, content=f"⚙️♻️ Reloaded `{mod.stem}`")


@with_annotated_args
@tj.as_slash_command('unload', "Removes a module.")
#
@tj.as_message_command('unload', 'ul')
async def unload_module(
    ctx: tj.abc.Context,
    module: t.Annotated[ja.Str, "Which module?", ja.Choices(modules_tup)],
):
    """Unload a module in tanjun"""

    if ctx.author.id not in c.__developers__:
        await err_say(ctx, content="🚫⚙️ Reserved for bot's developers only")
        return
    mod = modules[module]
    try:
        ctx.client.unload_modules(mod)
    except ValueError:
        await err_say(ctx, content=f"❗ Couldn't unload `{mod.stem}`")
        return

    await say(ctx, content=f"⚙️📤 Unloaded `{mod.stem}`")


@with_annotated_args
@tj.as_slash_command('load', "Loads a module.")
#
@tj.as_message_command('load', 'lo')
async def load_module(
    ctx: tj.abc.Context,
    module: t.Annotated[ja.Str, "Which module?", ja.Choices(modules_tup)],
):
    """Load a module in tanjun"""

    if ctx.author.id not in c.__developers__:
        await err_say(ctx, content="🚫⚙️ Reserved for bot's developers only")
        return
    mod = modules[module]
    try:
        ctx.client.load_modules(mod)
    except ValueError:
        await err_say(ctx, content=f"❗ Couldn't load `{mod.stem}`")
        return

    await say(ctx, content=f"⚙️📥 Loaded `{mod.stem}`")


@tj.as_message_command('delete_all_app_commands')
async def delete_all_app_commands(ctx: tj.abc.Context, bot: al.Injected[hk.GatewayBot]):
    if ctx.author.id not in c.__developers__:
        await err_say(ctx, content="🚫⚙️ Reserved for bot's developers only")
        return

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
