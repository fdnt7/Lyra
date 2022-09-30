import typing as t
import difflib as dfflib

import operator as op
import functools as ft

import hikari as hk
import tanjun as tj
import alluka as al

from ..lib.extras import groupby
from ..lib.utils import (
    LyraConfig,
    EmojiRefs,
    color_hash_obj,
    say,
)
from ..lib.cmd import (
    CommandIdentifier as C,
    Binds,
    AlmostGenericAnyCommandType,
    GenericCommandType,
    with_identifier,
    recurse_cmds,
    get_cmd_name,
    get_full_cmd_repr_from_identifier,
)
from ..lib.music import __init_component__


misc = __init_component__(__name__, guild_check=False)


# ~


all_cmds_sep: dict[str, list[GenericCommandType]] = {}
all_cmds_aliases: dict[tuple[str], list[GenericCommandType]] = {}
all_cmds_cat: dict[tj.abc.Component, dict[str, tuple[GenericCommandType]]] = {}


async def commands_autocomplete(ctx: tj.abc.AutocompleteContext, value: str, /):
    def _calc_ratio(_a_cmds: tuple[tuple[str], list[GenericCommandType]]):
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
async def on_started(
    _: hk.StartedEvent,
    client: al.Injected[tj.Client],
    bot: al.Injected[hk.GatewayBot],
    lfg: al.Injected[LyraConfig],
):
    me = bot.get_me()
    assert me

    decl_glob_cmds = lfg.decl_glob_cmds
    g = (
        (
            decl_glob_cmds[0]
            if isinstance(decl_glob_cmds, t.Sequence)
            else (
                decl_glob_cmds if not isinstance(decl_glob_cmds, bool) else hk.UNDEFINED
            )
        )
        if lfg.is_dev_mode
        else hk.UNDEFINED
    )

    slash = sorted(client.iter_slash_commands(), key=lambda cmd: cmd.name)
    slash_ = sorted(
        filter(
            lambda cmd: cmd.type is hk.CommandType.SLASH,
            await bot.rest.fetch_application_commands(me.id, g),
        ),
        key=lambda cmd: cmd.name,
    )

    class MockContext(t.NamedTuple):
        command: GenericCommandType

    for s, s_ in zip(slash, slash_, strict=True):
        s.set_tracked_command(s_)

    cmds_tup = t.cast(tuple[AlmostGenericAnyCommandType], (*client.iter_commands(),))
    for cmd in recurse_cmds(cmds_tup, keep_group_cmds=True):
        check = next(iter(cmd.checks))
        set_metadata = (
            check._checks[0]  # pyright: ignore [reportPrivateUsage]
            if isinstance(
                check, tj.checks._AllChecks  # pyright: ignore [reportPrivateUsage]
            )
            else check
        )
        set_metadata(MockContext(cmd))
        # print(f"{cmd}\n - {cmd.metadata}")

    _all_cmds_sep = groupby(cmds_tup, key=lambda c: c.metadata['identifier'])

    all_cmds_sep.update(_all_cmds_sep)
    all_cmds_aliases.update(
        {
            (ft.reduce(op.add, (get_cmd_name(cmd) for cmd in cmds))): cmds
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


@with_identifier(C.PING)
# -
@tj.as_slash_command('ping', "Shows the bot's latency", dm_enabled=True)
@tj.as_message_command('ping', 'latency', 'pi', 'lat', 'late', 'png')
async def ping_(ctx: tj.abc.Context):
    """
    Shows the bot's latency
    """
    assert ctx.shards
    await say(ctx, content=f"🏓 **{int(ctx.shards.heartbeat_latency*1000)}** ms")


# /help


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
    command: list[GenericCommandType],
    erf: al.Injected[EmojiRefs],
):
    # await err_say(ctx, content="⚡ This command is coming soon!")
    cmd = command[-1]
    component = cmd.component
    assert component

    identifier: C = cmd.metadata['identifier']
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
            title=f"📖 Manual for command `{identifier}`", description=desc, color=color
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
            f"For more info about the glossary and meanings of the symbols above, please check {get_full_cmd_repr_from_identifier(C.ABOUT, ctx, pretty=False)}"
        )
    )
    await say(ctx, embed=embed)


# -


loader = misc.load_from_scope().make_loader()
