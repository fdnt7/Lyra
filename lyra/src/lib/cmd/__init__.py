import typing as t

import tanjun as tj
import hikari as hk


from .ids import CommandIdentifier
from ..utils.types import (
    Contextish,
    GenericAnyCommandType,
    GenericAnySlashCommandType,
    GenericCommandType,
    MenuCommandType,
    MessageCommandGroupType,
    MessageCommandType,
    SlashCommandGroupType,
    SlashCommandType,
)
from ..extras.types import Option


def get_pref(ctx_: Contextish, /):
    if isinstance(ctx_, tj.abc.MessageContext):
        return next(iter(ctx_.client.prefixes))
    if isinstance(ctx_, tj.abc.SlashContext):
        return '/'
    if isinstance(ctx_, tj.abc.MenuContext):
        return '[>]'
    return ';;'


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


def get_full_cmd_repr(
    ctx_: Contextish,
    /,
    cmd: Option[GenericAnyCommandType] = None,
    *,
    pretty: bool = True,
):
    p = get_pref(ctx_)
    if not isinstance(ctx_, tj.abc.Context):
        if not cmd:
            raise RuntimeError(
                "Got `ctx` of type `ComponentInteraction` but `cmd` was `None`; No command object can be inferred."
            )
    else:
        cmd = cmd or t.cast(GenericAnyCommandType, ctx_.command)

    cmd_n = get_full_cmd_name(cmd)
    if isinstance(cmd, SlashCommandType | SlashCommandGroupType) and pretty:
        return f"</{cmd_n}:{get_cmd_id(cmd)}>"
    joined = ''.join((p, cmd_n))
    return ("`%s`" % joined) if pretty else joined


def get_full_cmd_repr_from_identifier(
    identifier: CommandIdentifier, /, ctx_: Contextish, *, pretty: bool = True
):
    from ..utils import get_client

    client = get_client(ctx_)
    if isinstance(ctx_, tj.abc.SlashContext):
        cmds = client.iter_slash_commands()
    elif isinstance(ctx_, tj.abc.MenuContext):
        cmds = client.iter_menu_commands()
    else:
        cmds = client.iter_message_commands()
    for cmd in cmds:
        if cmd.metadata['identifier'] == identifier:
            return get_full_cmd_repr(
                ctx_, t.cast(GenericAnyCommandType, cmd), pretty=pretty
            )
    raise NotImplementedError
