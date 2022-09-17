import typing as t

import hikari as hk
import tanjun as tj

from ..extras.types import Coro


EitherContext = tj.abc.MessageContext | tj.abc.AppCommandContext
Contextish = tj.abc.Context | hk.ComponentInteraction
"""A union "Context-ish" type hint. Includes:
* `tanjun.abc.Context` - A proper Context data
* `hikari.ComponentInteraction` - A similarly structured data"""

GuildInferableEvents = hk.GuildEvent | hk.VoiceEvent
"""A union type hint of events that can infer its guild id. Includes:
* `hikari.GuildEvent`
* `hikari.VoiceEvent`"""

GuildOrInferable = Contextish | hk.Snowflakeish | GuildInferableEvents
"""A union type hint of objects that can infer its guild id, or is the id itself. Includes:
* `hikari.Snowflakeish`
* `Contextish`
* `GuildInferableEvents`"""

RESTInferable = Contextish | GuildInferableEvents
"""A union type hint of objects that can infer its `hikari.api.RESTClient` client. Includes:
* `Contextish`
* `GuildInferableEvents`"""

GuildOrRESTInferable = GuildOrInferable | RESTInferable
"""A union type hint of objects that can infer its `hikari.api.RESTClient` client, its guild id, or is the id itself. Includes:
* `GuildOrInferable`
* `RESTInferable`"""

MaybeClientInferable = t.Any | tj.abc.Context

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

with_annotated_args = tj.annotations.with_annotated_args(follow_wrapped=True)
