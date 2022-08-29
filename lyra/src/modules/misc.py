import difflib as dfflib
import operator as op
import functools as ft

import hikari as hk
import tanjun as tj
import alluka as al

from ..lib.musicutils import __init_component__
from ..lib.compose import Binds
from ..lib.utils import (
    BaseCommandType,
    EmojiRefs,
    color_hash_obj,
    get_cmd_handle,
    get_cmd_trigger,
    say,
)
from ..lib.extras import groupby


misc = __init_component__(__name__, guild_check=False)


# ~


all_cmds_sep: dict[str, list[BaseCommandType]] = {}
all_cmds_aliases: dict[tuple[str], list[BaseCommandType]] = {}
all_cmds_cat: dict[tj.abc.Component, dict[str, tuple[BaseCommandType]]] = {}


async def commands_autocomplete(ctx: tj.abc.AutocompleteContext, value: str, /):
    def _calc_ratio(_a_cmds: tuple[tuple[str], list[BaseCommandType]]):
        return dfflib.SequenceMatcher(
            lambda n: not n,
            next(iter(dfflib.get_close_matches(value.casefold(), _a_cmds[0])), ''),
            value.casefold(),
        ).quick_ratio()

    match_pairs = dict(
        filter(
            lambda x: _calc_ratio(x),
            sorted(
                all_cmds_aliases.items(),
                key=lambda a_cmds: _calc_ratio(a_cmds),
                reverse=True,
            ),
        )
    )
    all_cmds_sep_rev = {(*(cmds),): a for a, cmds in all_cmds_sep.items()}
    matches = (*(all_cmds_sep_rev[tuple(cmds)] for cmds in match_pairs.values()),)
    await ctx.set_choices({v: v for v in matches[:25]})


@misc.with_listener()
async def on_started(_: hk.StartedEvent, client: al.Injected[tj.Client]):
    _all_cmds_iter = tuple(client.iter_commands())
    _all_cmds_sep = groupby(_all_cmds_iter, key=lambda cmd: get_cmd_handle(cmd))

    all_cmds_sep.update(_all_cmds_sep)
    all_cmds_aliases.update(
        {
            (ft.reduce(op.add, (get_cmd_trigger(cmd) for cmd in cmds))): cmds
            for cmds in _all_cmds_sep.values()
        }
    )
    all_cmds_cat.update(
        {
            c: dict(cmds)
            for c, cmds in groupby(
                all_cmds_sep.items(), key=lambda cmd: getattr(cmd[1][0], 'component')
            ).items()
        }
    )


# /ping


@tj.as_slash_command('ping', "Shows the bot's latency", dm_enabled=True)
#
@tj.as_message_command('ping', 'latency', 'pi', 'lat', 'late', 'png')
async def ping_(ctx: tj.abc.Context):
    """
    Shows the bot's latency
    """
    assert ctx.shards
    await say(ctx, content=f"🏓 **{int(ctx.shards.heartbeat_latency*1000)}** ms")


# /help


# TODO: #27 Implement `/help`
# @tj.with_str_slash_option(
#     'command',
#     "Which command?",
#     autocomplete=commands_autocomplete,
#     converters=lambda v: all_cmds_sep[v],
# )
# @tj.as_slash_command('help', "Shows the user manual of a command")
# #
# @tj.with_argument('command')
# @tj.as_message_command('help', 'h', 'man', 'manual')
async def help_(
    ctx: tj.abc.Context,
    command: list[BaseCommandType],
    erf: al.Injected[EmojiRefs],
):
    # await err_say(ctx, content="⚡ This command is coming soon!")
    cmd = command[-1]
    component = cmd.component
    assert component

    handle: str = get_cmd_handle(cmd)
    docs: str = getattr(cmd, 'callback').__doc__
    avail_in: list[hk.KnownCustomEmoji] = []
    if any(
        isinstance(_cmd, tj.SlashCommand | tj.SlashCommandGroup) for _cmd in command
    ):
        avail_in.append(erf['slash'])
    if any(
        isinstance(_cmd, tj.MessageCommand | tj.MessageCommandGroup) for _cmd in command
    ):
        avail_in.append(erf['prefix'])
    if any(isinstance(_cmd, tj.MenuCommand) for _cmd in command):
        avail_in.append(erf['menu'])

    desc = f"{' '.join(map(str, avail_in))}\n```{docs}```\n**Command Category**: `{component.name}`"

    color = color_hash_obj(component)
    embed = (
        hk.Embed(
            title=f"📖 Manual for command `{handle}`", description=desc, color=color
        )
        .add_field(
            'Checks',
            (
                '\n'.join(
                    f"- {check.__doc__}"
                    for check in (cmd.metadata.get('binds') or Binds.NONE).split()
                )
            )
            or '` - `',
        )
        .add_field(
            'Binds',
            (
                '\n'.join(
                    f"- {bind.__doc__}"
                    for bind in (cmd.metadata.get('binds') or Binds.NONE).split()
                )
            )
            or '` - `',
        )
        .set_footer(
            "For more info about the glossary and meanings of the symbols above, please check /about"
        )
    )
    await say(ctx, embed=embed)


# -


loader = misc.load_from_scope().make_loader()
