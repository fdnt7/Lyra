import typing as t

import hikari as hk
import tanjun as tj

from ..extras import Coro


AnyContextType = tj.abc.MessageContext | tj.abc.AppCommandContext
ContextishType = tj.abc.Context | hk.ComponentInteraction
"""A union "Context-ish" type hint. Includes:
* `tanjun.abc.Context` - A proper Context data
* `hikari.ComponentInteraction` - A similarly structured data"""

GuildAwareEventType = hk.GuildEvent | hk.VoiceEvent
"""A union type hint of events that can infer its guild id. Includes
* `hikari.GuildEvent`
* `hikari.VoiceEvent`"""

GuildOrAwareType = ContextishType | hk.Snowflakeish | GuildAwareEventType
"""A union type hint of objects that can infer its guild id, or is the id itself. Includes:
* `hikari.Snowflakeish`
* `Contextish`
* `GuildInferableEvents`"""

RESTAwareType = ContextishType | GuildAwareEventType
"""A union type hint of objects that can infer its `hikari.api.RESTClient` client. Includes:
* `Contextish`
* `GuildInferableEvents`"""

ButtonBuilderType = hk.api.ButtonBuilder[hk.api.ActionRowBuilder]
ConnectionInfo = dict[
    str, t.Any
]  # TODO: Remove this once lavasnek_rs use the correct type
SelectMenuBuilderType = hk.api.SelectMenuBuilder[hk.api.ActionRowBuilder]
EditableComponentsType = ButtonBuilderType | SelectMenuBuilderType
MentionableType = hk.GuildChannel | hk.Role | hk.Member
PartialMentionableType = hk.PartialUser | hk.PartialRole | hk.PartialChannel
JoinableChannelType = hk.GuildVoiceChannel | hk.GuildStageChannel

BindSig = t.Callable[..., Coro[bool]] | t.Callable[..., bool]

with_annotated_args_wrapped = tj.annotations.with_annotated_args(follow_wrapped=True)


@t.runtime_checkable
class MaybeGuildIDAware(t.Protocol):
    @property
    def guild_id(self) -> t.Optional[int]:
        ...


@t.runtime_checkable
class ChannelAware(t.Protocol):
    @property
    def channel_id(self) -> int:
        ...

    async def fetch_channel(self) -> hk.TextableChannel:
        ...


@t.runtime_checkable
class ClientAware(t.Protocol):
    @property
    def client(self) -> tj.abc.Client:
        ...


class Contextish(ChannelAware, t.Protocol):
    ...


@t.runtime_checkable
class PurelyRESTAware(t.Protocol):
    @property
    def rest(self) -> hk.api.RESTClient:
        ...


@t.runtime_checkable
class RESTAwareAware(t.Protocol):
    @property
    def app(self) -> hk.RESTAware:
        ...


class GuildContextish(Contextish, MaybeGuildIDAware, t.Protocol):
    @property
    def member(self) -> t.Optional[hk.Member]:
        ...


class ClientAwareGuildContextish(GuildContextish, ClientAware, t.Protocol):
    ...


@t.runtime_checkable
class IntCastable(t.Protocol):
    def __int__(self) -> int:
        ...
