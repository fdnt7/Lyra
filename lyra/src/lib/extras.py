import os
import time
import enum as e
import typing as t
import inspect
import pathlib as pl
import functools as ft
import itertools as it
import collections as cl

# pyright: reportUnusedImport=false
from ._extras_types import (
    Option,
    Decorator,
    _DecoratedT,  # pyright: ignore [reportPrivateUsage]
    Result,
    Panic,
    NULL,
    RGBTriplet,
    MaybeIterable,
    URLstr,
)
from ._extras_vars import time_regex, time_regex_2, url_regex, loop
from ._extras_untyped import (
    limit_bytes_img_size,
    get_img_pallete,
    get_thumbnail,
    get_lyrics,
    url_to_bytesio,
)
from .consts import LOG_PAD


class AutoDocsFlag(e.Flag):
    """
    An implementation of python's `Flag` with documentation support

    Usage:
    ```
    class A(AutoDocsFlag):
        a = \"\"\"docs for a\"\"\", value_for_a

    >>> A.a.__doc__
    >>> "docs for a"
    ```
    """

    def __new__(cls, _doc: str, value: Option[int] = None, *_other: t.Any):
        obj = object.__new__(cls)
        obj._value_ = (
            (1 if not len(cls) else (((*cls,)[-1].value << 1) or 1))
            if value is None
            else value
        )
        return obj

    def __init__(self, doc: str, *_: t.Any):
        self.__doc__ = doc

    def split(self):
        return frozenset(e for e in self.__class__ if self & e)


class AutoDocsEnum(e.Enum):
    """
    An implementation of python's `Enum` with documentation support

    Usage:
    ```
    class A(AutoDocsEnum):
        a = \"\"\"docs for a\"\"\", value_for_a

    >>> A.a.__doc__
    >>> "docs for a"
    ```
    """

    def __new__(cls, _doc: str, value: Option[int] = None, *_other: t.Any):
        obj = object.__new__(cls)
        obj._value_ = (
            (1 if not len(cls) else (((*cls,)[-1].value + 1) or 1))
            if value is None
            else value
        )
        return obj

    def __init__(self, doc: str, *_: t.Any):
        self.__doc__ = doc


def curr_time_ms() -> int:
    return time.time_ns() // 1_000_000


def to_stamp(ms: int, /) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return (
        (f'{h:02}:' if h else '')
        + f'{m:02}:{s:02}'
        + (f'.{ms:03}' if not (h or m or s) else '')
    )


def to_ms(str_: str, /) -> Result[int]:
    VALID_FORMAT = "00:00.204 1:57 2:00:09 400ms 7m51s 5h2s99ms".split()
    singl_z = ['0']
    if match := time_regex.fullmatch(str_):
        match_ = singl_z + [*match.groups('0')]
        match_ += singl_z * (7 - len(match.groups()))
        ms = int(match_[6])
        s = int(match_[4])
        m = int(match_[3])
        h = int(match_[2])
    elif match := time_regex_2.fullmatch(str_):
        match_ = singl_z + list(match.groups('0'))
        match_ += singl_z * (9 - len(match.groups()))
        ms = int(match_[8])
        s = int(match_[6])
        m = int(match_[4])
        h = int(match_[2])
    else:
        raise ValueError(
            f"Invalid timestamp format given. Must be in the following format:\n> {fmt_str(VALID_FORMAT)}"
        )
    return (((h * 60 + m) * 60 + s)) * 1000 + ms


def wr(
    str_: str,
    limit: int = 60,
    replace_with: str = '…',
    /,
    *,
    block_friendly: bool = True,
) -> str:
    str_ = str_.replace("'", '′').replace('"', '″') if block_friendly else str_
    return (
        str_ if len(str_) <= limit else str_[: limit - len(replace_with)] + replace_with
    )


def format_flags(flags: e.Flag, /) -> str:
    return ' & '.join(f.replace('_', ' ').title() for f in str(flags).split('|'))


_TE = t.TypeVar('_TE')


def chunk(seq: t.Sequence[_TE], n: int, /) -> t.Generator[t.Sequence[_TE], None, None]:
    """Yield successive `n`-sized chunks from `seq`."""
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def chunk_b(
    seq: t.Sequence[_TE], n: int, /
) -> t.Generator[t.Sequence[_TE], None, None]:
    """Yield successive `n`-sized chunks from `seq`, backwards."""
    start = 0
    for end in range(len(seq) % n, len(seq) + 1, n):
        yield seq[start:end]
        start = end


def inj_glob(pattern: str, /):
    if os.environ.get('IN_DOCKER', False):
        p = pl.Path('.') / 'shared'
    else:
        p = pl.Path('.') / '..'
    return p.glob(pattern)


_CE = t.TypeVar('_CE')


def uniquify(iter_: t.Iterable[_CE], /) -> t.Iterable[_CE]:
    return (*(k for k, _ in it.groupby(iter_)),)


def join_and(
    str_iter: t.Iterable[str], /, *, sep: str = ', ', and_: str = ' and '
) -> str:
    l = (*filter(lambda e: e, str_iter),)
    return sep.join((*l[:-2], *[and_.join(l[-2:])]))


_FE = t.TypeVar('_FE')


def flatten(iter_iters: t.Iterable[t.Iterable[_FE]], /) -> t.Iterable[_FE]:
    return (*(val for sublist in iter_iters for val in sublist),)


def split_preset(str_: str, /, *, sep_1: str = ',', sep_2: str = '|'):
    return tuple(frozenset(v.split(sep_2)) for v in str_.split(sep_1))


def fmt_str(iter_strs: t.Iterable[str], /, *, sep: str = ', ') -> str:
    return sep.join('\"%s\"' % s for s in iter_strs)


def composed(*decs: Decorator[_DecoratedT]) -> Decorator[_DecoratedT]:
    def decorator(f: _DecoratedT) -> _DecoratedT:
        for dec in reversed(decs):
            f = dec(f)
        return f

    return decorator


__E = t.TypeVar('__E')
_KE = t.TypeVar('_KE')


def groupby(
    seq: t.Iterable[__E], /, *, key: t.Callable[[__E], _KE] = lambda e: e
) -> dict[_KE, list[__E]]:
    d: dict[_KE, list[__E]] = cl.defaultdict(list)
    return ft.reduce(lambda grp, val: grp[key(val)].append(val) or grp, seq, d)


def lgfmt(dunder_name: str, /) -> str:
    return f"{'.'.join(dunder_name.split('.')[1:]):<{LOG_PAD}}"


_P = t.ParamSpec('_P')


@t.overload
def void(f: t.Callable[_P, int]) -> t.Callable[_P, None]:
    ...


@t.overload
def void(f: t.Callable[_P, t.Awaitable[int]]) -> t.Callable[_P, t.Awaitable[None]]:
    ...


def void(f: t.Callable[_P, t.Any]) -> t.Callable[_P, None | t.Awaitable[None]]:
    def inner(*args: _P.args, **kwargs: _P.kwargs):
        f(*args, **kwargs)

    async def coro_inner(*args: _P.args, **kwargs: _P.kwargs):
        await f(*args, **kwargs)

    if inspect.iscoroutinefunction(f):
        return coro_inner
    return inner
