import typing as t

import hikari as hk
import tanjun as tj

from hikari.permissions import Permissions as hkperms

from ..extras import format_flags


EmojiRefs = t.NewType('EmojiRefs', dict[str, hk.KnownCustomEmoji])
base_h = tj.AnyHooks()
guild_c = tj.checks.GuildCheck(
    error_message="🙅 Commands can only be used in guild channels"
)

RESTRICTOR = hkperms.MANAGE_CHANNELS | hkperms.MANAGE_ROLES
DJ_PERMS: t.Final = hkperms.MOVE_MEMBERS
dj_perms_fmt: t.Final = format_flags(DJ_PERMS)
