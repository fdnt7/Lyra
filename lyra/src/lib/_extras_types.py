import typing as t

import attr as a


@a.define(hash=True, init=False, frozen=True)
class NullType(object):
    def __bool__(self) -> t.Literal[False]:
        return False


_S_co = t.TypeVar('_S_co', bound=t.Any, covariant=True)
NULL = NullType()
NullOr = _S_co | NullType

RGBTriplet = tuple[int, int, int]
URLstr = str


_T = t.TypeVar('_T')
_E = t.TypeVar('_E', bound=Exception)
_T_co = t.TypeVar('_T_co', covariant=True)
Coro = t.Coroutine[t.Any, t.Any, _T]
Option = _T | None
Result = t.Annotated[_T | t.NoReturn, ...]
Panic = t.Annotated[_T | t.NoReturn, ...]
Require = t.Annotated[_T_co, ...]
MaybeIterable = _T | t.Iterable[_T]
AsyncVoidFunction = t.Callable[..., t.Awaitable[None]]

OptionResult = Option[Result[_T]]

_DecoratedT = t.TypeVar('_DecoratedT')
Decorator = t.Callable[[_DecoratedT], _DecoratedT]
