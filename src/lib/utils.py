import re
import time
import enum as e
import asyncio
import logging
import aiohttp
import random as rd
import hashlib as hl
import traceback as tb
import hikari.messages as hk_msg
import tanjun as tj
import lyricsgenius as le

from difflib import SequenceMatcher
from functools import reduce
from contextlib import asynccontextmanager, nullcontext
from ytmusicapi import YTMusic

from .errors import *


Contextish = tj.abc.Context | hk.Snowflakeish


TIME_REGEX = re.compile(
    r"^((\d+):)?([0-5][0-9]|[0-9]):([0-5][0-9]|[0-9])(.([0-9]{1,3}))?$"
)
TIME_REGEX_2 = re.compile(
    r"^(?!\s*$)((\d+)h)?(([0-9]|[0-5][0-9])m)?(([0-9]|[0-5][0-9])s)?(([0-9]|[0-9][0-9]|[0-9][0-9][0-9])ms)?$"
)
YOUTUBE_REGEX = re.compile(
    r"^(?:https?:)?(?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]{7,15})(?:[\?&][a-zA-Z0-9\_-]+=[a-zA-Z0-9\_-]+)*(?:[&\/\#].*)?$"
)
URL_REGEX = re.compile(
    r'^(?:http|ftp)s?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$',
    re.I,
)
LYRICS_URL = 'https://some-random-api.ml/lyrics?title='

TIMEOUT = 60

hooks = tj.AnyHooks()
loop = asyncio.get_event_loop()
ytmusic = YTMusic()


@a.define
class RemovedSentinel:
    pass


REMOVED = RemovedSentinel()


async def _del_after(ctx: tj.abc.Context, delete_after: float, msg: hk.Message):
    await asyncio.sleep(delete_after)
    ch = await ctx.fetch_channel()
    await ch.delete_messages(msg)


async def err_reply(ctx: tj.abc.Context, **kwargs: t.Any):
    if isinstance(ctx, tj.abc.MessageContext):
        msg = await ctx.respond(**kwargs, reply=True)
        try:
            return msg
        finally:
            asyncio.create_task(_del_after(ctx, 3.5, msg))
    assert isinstance(ctx, tj.abc.SlashContext)
    if ctx.has_responded:
        await ctx.create_followup(**kwargs, flags=hk.MessageFlag.EPHEMERAL)
        return
    try:
        return await ctx.create_initial_response(
            **kwargs, flags=hk.MessageFlag.EPHEMERAL
        )
    except (hk.NotFoundError, RuntimeError):
        return await ctx.edit_initial_response(**kwargs)


async def hid_reply(ctx: tj.abc.Context, **kwargs: t.Any):
    if isinstance(ctx, tj.abc.MessageContext):
        await ctx.respond(**kwargs, reply=True)
        return
    assert isinstance(ctx, tj.abc.SlashContext)
    if ctx.has_responded:
        await ctx.create_followup(**kwargs, flags=hk.MessageFlag.EPHEMERAL)
        return
    return await ctx.create_initial_response(**kwargs, flags=hk.MessageFlag.EPHEMERAL)


async def def_reply(ctx: tj.abc.Context, **kwargs: t.Any):
    if isinstance(ctx, tj.abc.MessageContext):
        return await ctx.respond(**kwargs, reply=True)

    assert isinstance(ctx, tj.abc.SlashContext)
    try:
        return await ctx.create_initial_response(
            **kwargs, flags=hk.MessageFlag.EPHEMERAL
        )
    except (hk.NotFoundError, RuntimeError):
        return await ctx.edit_initial_response(**kwargs)


async def reply(ctx: tj.abc.Context, delete_after: float = 0.0, **kwargs):
    if isinstance(ctx, tj.abc.MessageContext):
        msg = await ctx.respond(**kwargs, reply=True)
    else:
        assert isinstance(ctx, tj.abc.SlashContext)
        if ctx.has_responded:
            msg = await ctx.create_followup(**kwargs)
        else:
            msg = await ctx.create_initial_response(**kwargs)
            msg = await ctx.fetch_initial_response()

    try:
        return msg
    finally:
        if delete_after:
            asyncio.create_task(_del_after(ctx, delete_after, msg))


def disable_buttons(
    rest: hk.api.RESTClient,
    *action_rows: hk.api.ActionRowBuilder,
    predicates: t.Callable[
        [hk.api.InteractiveButtonBuilder[hk.api.ActionRowBuilder]], bool
    ] = lambda _: True,
) -> tuple[hk.api.ActionRowBuilder, ...]:
    action_rows_ = list(action_rows)
    for a in action_rows_:
        components = a.components
        a = rest.build_action_row()
        for c in map(
            lambda c_: c_.set_is_disabled(True)
            if isinstance(c_, hk.api.ButtonBuilder) and predicates(c)
            else c_,
            components,
        ):
            assert isinstance(c, hk.api.ButtonBuilder)
            a.add_component(c)
    return tuple(action_rows_)


def trigger_thinking(flags: hk.MessageFlag = hk.MessageFlag.NONE):
    def decorator(func: t.Callable[..., t.Coroutine]):
        async def wrapper(ctx: tj.abc.Context, *args: t.Any, **kwargs: t.Any):
            assert ctx.guild_id is not None
            if isinstance(ctx, tj.abc.MessageContext):
                ch = ctx.get_channel()
                assert ch is not None
                async with ch.trigger_typing():
                    await func(ctx, *args, **kwargs)
                return

            assert isinstance(ctx, tj.abc.SlashContext)
            try:
                if not ctx.has_responded:
                    await ctx.defer(flags)
            except RuntimeError:
                pass
            await func(ctx, *args, **kwargs)

        return wrapper

    return decorator


@hooks.with_on_parser_error
async def on_parser_error(ctx: tj.abc.Context, error: tj.errors.ParserError) -> None:
    await err_reply(ctx, content=f"❌ You've given an invalid input: `{error}`")


def curr_time_ms() -> int:
    return time.time_ns() // 1_000_000


def ms_stamp(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return (
        (f'{h:02}:' if h else '')
        + f'{m:02}:{s:02}'
        + (f'.{ms:03}' if not (h or m or s) else '')
    )


def stamp_ms(str_: str) -> int:
    VALID_FORMAT = "00:00.204, 1:57, 2:00:09 | 400ms, 7m51s, 5h2s99ms"
    singl_z = ['0']
    if match := TIME_REGEX.fullmatch(str_):
        match_ = singl_z + list(match.groups('0'))
        match_ += singl_z * (7 - len(match.groups()))
        ms = int(match_[6])
        s = int(match_[4])
        m = int(match_[3])
        h = int(match_[2])
    elif match := TIME_REGEX_2.fullmatch(str_):
        match_ = singl_z + list(match.groups('0'))
        match_ += singl_z * (9 - len(match.groups()))
        ms = int(match_[8])
        s = int(match_[6])
        m = int(match_[4])
        h = int(match_[2])
    else:
        raise InvalidArgument(Argument(str_, VALID_FORMAT))
    return (((h * 60 + m) * 60 + s)) * 1000 + ms


def wrap(str_: str, limit: int = 60) -> str:
    return str_ if len(str_) <= limit else str_[: limit - 3] + '...'


def format_flags(flags: e.Flag) -> str:
    return ' & '.join(f.replace('_', ' ').title() for f in str(flags).split('|'))


def snowflakeify(ctx_g: Contextish):
    if isinstance(ctx_g, tj.abc.Context):
        assert ctx_g.guild_id is not None
        ctx_g = ctx_g.guild_id
    return ctx_g
