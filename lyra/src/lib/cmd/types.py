import typing as t

import hikari as hk
import tanjun as tj

from ..extras import AsyncVoidAnySig


CommandType = tj.abc.ExecutableCommand
GenericCommandType = CommandType[tj.abc.Context]
MenuCommandType = tj.abc.MenuCommand
GenericMenuCommandType = MenuCommandType[
    AsyncVoidAnySig, t.Literal[hk.CommandType.MESSAGE]
]
MessageCommandType = tj.abc.MessageCommand
GenericMessageCommandType = MessageCommandType[AsyncVoidAnySig]
MessageCommandGroupType = tj.abc.MessageCommandGroup
GenericMessageCommandGroupType = MessageCommandGroupType[AsyncVoidAnySig]
GenericAnyMessageCommandType = (
    GenericMessageCommandType | GenericMessageCommandGroupType
)
SlashCommandType = tj.abc.SlashCommand
GenericSlashCommandType = SlashCommandType[AsyncVoidAnySig]
SlashCommandGroupType = tj.abc.SlashCommandGroup
GenericAnySlashCommandType = GenericSlashCommandType | tj.abc.SlashCommandGroup
GenericAnyCommandType = (
    GenericMenuCommandType | GenericAnySlashCommandType | GenericAnyMessageCommandType
)
AlmostGenericAnyCommandType = (
    tj.abc.BaseSlashCommand | GenericMenuCommandType | GenericMessageCommandType
)
GenericAnyChildCommandType = GenericSlashCommandType | GenericMessageCommandType
GenericAnyCommandGroupType = tj.abc.SlashCommandGroup | GenericMessageCommandGroupType
