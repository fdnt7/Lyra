import re
import time
import enum as e
import asyncio
import logging
import typing as t
import random as rd
import hashlib as hl
import hikari as hk
import tanjun as tj
import traceback as tb
import lavasnek_rs as lv


from difflib import SequenceMatcher
from base64 import b64encode, b64decode, standard_b64decode
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from hikari.messages import ButtonStyle
from hikari.permissions import Permissions as P


TIME_REGEX = re.compile(
    r"^((\d+):)?([0-5][0-9]|[0-9]):([0-5][0-9]|[0-9])(.([0-9]{1,3}))?$"
)
TIME_REGEX_2 = re.compile(
    r"^(?!\s*$)((\d+)h)?(([0-9]|[0-5][0-9])m)?(([0-9]|[0-5][0-9])s)?(([0-9]|[0-9][0-9]|[0-9][0-9][0-9])ms)?$"
)

T = t.TypeVar("T")

hooks = tj.AnyHooks()


async def err_reply(ctx: tj.abc.Context, **kwargs):
    if isinstance(ctx, tj.abc.MessageContext):
        await ctx.respond(**kwargs, reply=True)
        await asyncio.sleep(3.5)
        return await ctx.delete_initial_response()
    assert isinstance(ctx, tj.abc.SlashContext)
    return await ctx.create_initial_response(**kwargs, flags=hk.MessageFlag.EPHEMERAL)


async def hid_reply(ctx: tj.abc.Context, **kwargs):
    if isinstance(ctx, tj.abc.MessageContext):
        return await ctx.respond(**kwargs, reply=True)
    assert isinstance(ctx, tj.abc.SlashContext)
    return await ctx.create_initial_response(**kwargs, flags=hk.MessageFlag.EPHEMERAL)


async def def_reply(ctx: tj.abc.Context, **kwargs):
    if isinstance(ctx, tj.abc.MessageContext):
        return await ctx.respond(**kwargs, reply=True)
    return await ctx.edit_initial_response(**kwargs)


async def reply(ctx: tj.abc.Context, **kwargs):
    if isinstance(ctx, tj.abc.MessageContext):
        return await ctx.respond(**kwargs, reply=True)
    assert isinstance(ctx, tj.abc.SlashContext)
    return await ctx.create_initial_response(**kwargs)


@hooks.with_on_parser_error
async def on_parser_error(ctx: tj.abc.Context, error: tj.errors.ParserError) -> None:
    await err_reply(ctx, content=f"❌ You've given an invalid input: `{error}`")


def curr_time_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass
class Argument(t.Generic[T]):
    got: T
    expected: T


class BaseMusicCommandException(Exception):
    pass


@dataclass
class BadArgument(BaseMusicCommandException):
    arg: Argument


class InvalidArgument(BadArgument):
    pass


class IllegalArgument(BadArgument):
    pass


def ms_stamp(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return (
        (f"{h:02}:" if h else "")
        + f"{m:02}:{s:02}"
        + (f".{ms:03}" if not (h or m or s) else "")
    )


def stamp_ms(str_: str) -> int:
    VALID_FORMAT = "00:00.204, 1:57, 2:00:09 | 400ms, 7m51s, 5h2s99ms"
    singl_z = ["0"]
    if match := TIME_REGEX.fullmatch(str_):
        match_ = singl_z + list(match.groups("0"))
        match_ += singl_z * (7 - len(match.groups()))
        ms = int(match_[6])
        s = int(match_[4])
        m = int(match_[3])
        h = int(match_[2])
    elif match := TIME_REGEX_2.fullmatch(str_):
        match_ = singl_z + list(match.groups("0"))
        match_ += singl_z * (9 - len(match.groups()))
        ms = int(match_[8])
        s = int(match_[6])
        m = int(match_[4])
        h = int(match_[2])
    else:
        raise InvalidArgument(Argument(str_, VALID_FORMAT))
    return (((h * 60 + m) * 60 + s)) * 1000 + ms


def wrap(str_: str, limit=60) -> str:
    return str_ if len(str_) <= limit else str_[: limit - 3] + "..."


def format_flags(flags: e.Flag) -> str:
    return " & ".join(f.replace("_", " ").title() for f in str(flags).split("|"))
