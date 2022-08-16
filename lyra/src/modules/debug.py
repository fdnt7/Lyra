import logging
import pathlib as pl

import hikari as hk
import tanjun as tj
import alluka as al

from ..lib.flags import as_developer_check
from ..lib.musicutils import init_component
from ..lib.extras import lgfmt
from ..lib.utils import say, err_say


debug = init_component(
    __name__, guild_check=False, music_hook=False, other_checks={as_developer_check}
)


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


modules = {p.stem: p for p in pl.Path('.').glob('./src/modules/*.py')}
choices = (*modules,)


@tj.with_str_slash_option('module', "The module to target.", choices=choices)
@tj.as_slash_command('reload', "Reloads a module.")
#
@tj.with_argument('module')
@tj.as_message_command('reload', 'rl')
async def reload_module(
    ctx: tj.abc.Context,
    module: str,
    client: al.Injected[tj.Client],
):
    """Reload a module in tanjun"""

    mod = modules[module]
    try:
        client.reload_modules(mod)
    except ValueError:
        client.load_modules(mod)

    await say(ctx, content=f"⚙️♻️ Reloaded `{mod.stem}`")


@tj.with_str_slash_option('module', "The module to target.", choices=choices)
@tj.as_slash_command('unload', "Removes a module.")
#
@tj.with_argument('module')
@tj.as_message_command('unload', 'ul')
async def unload_module(
    ctx: tj.abc.Context,
    module: str,
    client: al.Injected[tj.Client],
):
    """Unload a module in tanjun"""

    mod = modules[module]
    try:
        client.unload_modules(mod)
    except ValueError:
        await err_say(ctx, content=f"❗ Couldn't unload `{mod.stem}`")
        return

    await say(ctx, content=f"⚙️📤 Unloaded `{mod.stem}`")


@tj.with_str_slash_option('module', "The module to reload.", choices=choices)
@tj.as_slash_command(
    'load',
    "Loads a module.",
)
#
@tj.with_argument('module')
@tj.as_message_command('load', 'lo')
async def load_module(
    ctx: tj.abc.Context,
    module: str,
    client: al.Injected[tj.Client],
):
    """Load a module in tanjun"""

    mod = modules[module]
    try:
        client.load_modules(mod)
    except ValueError:
        await err_say(ctx, content=f"❗ Couldn't load `{mod.stem}`")
        return

    await say(ctx, content=f"⚙️📥 Loaded `{mod.stem}`")


@tj.as_message_command('delete_all_global_commands')
async def delete_all_app_commands(ctx: tj.abc.Context, bot: al.Injected[hk.GatewayBot]):
    """Deletes all global commands"""

    me = bot.get_me()
    assert me
    cmds = await bot.rest.fetch_application_commands(me.id)
    L = len(cmds)
    await ctx.respond("...")
    for i, cmd in enumerate(cmds, 1):
        await cmd.delete()
        logger.debug(f"Deleting global application commands {i}/{L} ({cmd.name})")
    await ctx.respond("Done")


# -


loader = debug.load_from_scope().make_loader()
