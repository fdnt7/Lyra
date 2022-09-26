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
_P = t.ParamSpec('_P')
_E = t.TypeVar('_E', bound=Exception)
_T_co = t.TypeVar('_T_co', covariant=True)
__E = t.TypeVar('__E')
_KE = t.TypeVar('_KE')

Coro = t.Coroutine[t.Any, t.Any, _T]
Option = _T | None
Result = t.Annotated[_T | t.NoReturn, ...]
OptionResult = Option[Result[_T]]
Panic = t.Annotated[_T | t.NoReturn, ...]
Require = t.Annotated[_T_co, ...]
AnyOr = t.Any | _T
IterableOr = _T | t.Iterable[_T]

KeySig = t.Callable[[__E], _KE]
MapSig = t.Callable[[_T], _T]
VoidSig = t.Callable[[_T], None]
VoidAnySig = t.Callable[..., None]
PredicateSig = t.Callable[[_T], bool]
AsyncVoidSig = t.Callable[[_T], Coro[None]]
AsyncVoidAnySig = t.Callable[..., Coro[None]]
DecorateSig = t.Callable[[_T], _T]
ArgsDecorateSig = t.Callable[_P, DecorateSig[_T]]
