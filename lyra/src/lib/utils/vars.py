import typing as t

import hikari as hk
import tanjun as tj

from ..extras import format_flags


EmojiCache = t.NewType('EmojiCache', dict[str, hk.KnownCustomEmoji])
base_h = tj.AnyHooks()
guild_c = tj.checks.GuildCheck(
    error_message="🙅 Commands can only be used in guild channels"
)

RESTRICTOR = hk.Permissions.MANAGE_CHANNELS | hk.Permissions.MANAGE_ROLES
DJ_PERMS: t.Final = hk.Permissions.MOVE_MEMBERS
dj_perms_fmt: t.Final = format_flags(DJ_PERMS)
