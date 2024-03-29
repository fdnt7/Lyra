import typing as t
import functools as ft

import tanjun as tj
import hikari as hk

from ..extras import RecurserSig, Option, recurse
from ..utils import ContextishType, get_client
from .types import (
    AlmostGenericAnyCommandType,
    GenericAnyCommandGroupType,
    GenericAnyCommandType,
    GenericAnySlashCommandType,
    GenericCommandType,
    MenuCommandType,
    MessageCommandGroupType,
    MessageCommandType,
    SlashCommandGroupType,
    SlashCommandType,
)
from .ids import CommandIdentifier


def get_implied_prefix(ctx_cmd: ContextishType | GenericAnyCommandType, /) -> str:
    if isinstance(ctx_cmd, tj.abc.MessageContext):
        return next(iter(ctx_cmd.client.prefixes))
    if isinstance(
        ctx_cmd, tj.abc.SlashContext | SlashCommandType | SlashCommandGroupType
    ):
        return '/'
    if isinstance(ctx_cmd, tj.abc.MenuContext | MenuCommandType):
        return '|> '

    client = get_client(ctx_cmd)
    return next(iter(client.prefixes))


def get_cmd_name(cmd: GenericCommandType, /) -> tuple[str]:
    if isinstance(cmd, SlashCommandGroupType | SlashCommandType):
        return (cmd.name,)
    if isinstance(cmd, MessageCommandGroupType | MessageCommandType):
        return (*cmd.names,)
    if isinstance(cmd, MenuCommandType):
        return (cmd.name,)
    raise NotImplementedError


def get_full_cmd_name(cmd: GenericCommandType, /):
    def _recurse(_cmd: GenericAnyCommandType, _names: list[str]) -> list[str]:
        if isinstance(_cmd, MenuCommandType):
            _names.append(_cmd.name)
            return _names
        if isinstance(_cmd, MessageCommandGroupType | MessageCommandType):
            _names.append(next(iter(_cmd.names)))
        else:
            _names.append(_cmd.name)

        if not (parent_cmd := _cmd.parent):
            return _names
        return _recurse(parent_cmd, _names)

    return ' '.join(_recurse(t.cast(GenericAnyCommandType, cmd), [])[::-1])


def get_cmd_id(cmd: GenericAnySlashCommandType, /) -> hk.Snowflake:
    def _recurse(_cmd: GenericAnySlashCommandType) -> hk.Snowflake:
        if _id := _cmd.tracked_command_id:
            return _id

        assert _cmd.parent
        return _recurse(_cmd.parent)

    return _recurse(cmd)


@t.overload
def get_full_cmd_repr(
    ctx: tj.abc.Context,
    /,
    cmd: Option[GenericAnyCommandType] = None,
    *,
    pretty: bool = True,
) -> str:
    ...


@t.overload
def get_full_cmd_repr(
    ctx_: hk.ComponentInteraction,
    /,
    cmd: GenericAnySlashCommandType,
    *,
    pretty: bool = True,
) -> str:
    ...


@t.overload
def get_full_cmd_repr(
    _: None, /, cmd: GenericAnySlashCommandType, *, pretty: bool = True
) -> str:
    ...


def get_full_cmd_repr(
    _ctx_: Option[ContextishType],
    /,
    cmd: Option[GenericAnyCommandType] = None,
    *,
    pretty: bool = True,
):
    if not isinstance(_ctx_, tj.abc.Context):
        if not cmd:
            raise RuntimeError(
                "Got `ctx` not of type `tj.abc.Context` but `cmd` was `None`; No command object can be inferred."
            )
    else:
        cmd = cmd or t.cast(GenericAnyCommandType, _ctx_.command)

    cmd_n = get_full_cmd_name(cmd)
    if isinstance(cmd, SlashCommandType | SlashCommandGroupType) and pretty:
        return f"</{cmd_n}:{get_cmd_id(cmd)}>"

    p = get_implied_prefix(cmd)
    joined = ''.join((p, cmd_n))
    return ("`%s`" % joined) if pretty else joined


@t.overload
def get_full_cmd_repr_from_identifier(
    identifier: CommandIdentifier, /, ctx_: ContextishType, *, pretty: bool = True
) -> str:
    ...


@t.overload
def get_full_cmd_repr_from_identifier(
    identifier: CommandIdentifier, /, client: tj.abc.Client, *, pretty: bool = True
) -> str:
    ...


def get_full_cmd_repr_from_identifier(
    identifier: CommandIdentifier,
    /,
    _ctx_c: ContextishType | tj.abc.Client,
    *,
    pretty: bool = True,
):
    client = _ctx_c if isinstance(_ctx_c, tj.abc.Client) else get_client(_ctx_c)
    _ctx_ = None if isinstance(_ctx_c, tj.abc.Client) else _ctx_c
    if not _ctx_ or isinstance(_ctx_, tj.abc.SlashContext):
        cmds = client.iter_slash_commands()
    elif isinstance(_ctx_, tj.abc.MenuContext):
        cmds = client.iter_menu_commands()
    else:
        cmds = client.iter_message_commands()

    for cmd in recurse_cmds(cmds, keep_group_cmds=True):
        if cmd.metadata['identifier'] == identifier:
            if _ctx_:
                return get_full_cmd_repr(
                    _ctx_, t.cast(GenericAnySlashCommandType, cmd), pretty=pretty
                )
            return get_full_cmd_repr(
                _ctx_, t.cast(GenericAnySlashCommandType, cmd), pretty=pretty
            )
    raise NotImplementedError


def recurse_cmds(
    cmds: t.Iterable[AlmostGenericAnyCommandType], /, *, keep_group_cmds: bool = False
) -> t.Iterator[AlmostGenericAnyCommandType]:
    recurse_part = ft.partial(
        recurse,
        recursed=tj.abc.SlashCommandGroup
        | MessageCommandGroupType,  # pyright: ignore [reportGeneralTypeIssues]
        include_recursed=keep_group_cmds,
    )
    recurser: RecurserSig[
        GenericAnyCommandGroupType, AlmostGenericAnyCommandType
    ] = lambda c: (
        _c
        for _c in recurse_part(
            c.commands,
            recurser=recurser,
        )
    )
    yield from recurse_part(cmds, recurser=recurser)
