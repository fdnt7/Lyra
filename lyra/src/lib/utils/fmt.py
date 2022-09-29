import enum as e
import itertools as it

from ..extras import Option, join_truthy, split_flags


ANSI_BLOCK = "```ansi\n%s\n```"

__format = "\u001b[%sm"
__reset = "\u001b[0m"


class Style(e.IntFlag):
    _ = 0
    """Normal"""
    B = 1
    """Bold"""
    U = 4
    """Underline"""


class Fore(e.Enum):
    D = 30
    """Grey"""
    R = 31
    """Red"""
    G = 32
    """Green"""
    Y = 33
    """Yellow"""
    B = 34
    """Blue"""
    M = 35
    """Magenta"""
    C = 36
    """Cyan"""
    W = 37
    """White"""


class Back(e.Enum):
    B = 40
    """Firefly Dark Blue"""
    O = 41
    """Orange"""
    M = 42
    """Marble Blue"""
    T = 43
    """Greyish Turquoise"""
    G = 44
    """Grey"""
    I = 45
    """Indigo"""
    L = 46
    """Light Grey"""
    W = 47
    """White"""


def cl(
    str_: str,
    /,
    style: Option[Style] = None,
    back: Option[Back] = None,
    fore: Option[Fore] = None,
    *,
    reset: bool = False,
    block_fmt: bool = False,
) -> str:
    args = it.chain(
        map(lambda f: str(f.value), split_flags(style) if style else {Style._}),
        map(lambda f: str(f.value) if f else '', (back, fore)),
    )
    _fmt = join_truthy(args, ';')
    formatted = f"{__format % _fmt}{str_}{__reset if reset else ''}"
    if block_fmt:
        return ANSI_BLOCK % formatted
    return formatted
