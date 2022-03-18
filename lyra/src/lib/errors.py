import abc
import typing as t

import attr as a
import hikari as hk
import lavasnek_rs as lv


from hikari.permissions import Permissions as hkperms


_A = t.TypeVar('_A')


@a.define
class Argument(t.Generic[_A]):
    got: _A
    expected: _A


@a.define(init=False)
class BaseMusicCommandException(abc.ABC, Exception):
    pass


_A_b = t.TypeVar('_A_b')


@a.define
class BadArgument(BaseMusicCommandException, t.Generic[_A_b]):
    arg: Argument[_A_b]


_A_i = t.TypeVar('_A_i')


@a.define(init=False)
class InvalidArgument(BadArgument[_A_i]):
    pass


_A_x = t.TypeVar('_A_x')


@a.define(init=False)
class IllegalArgument(BadArgument[_A_x]):
    pass


@a.define(init=False)
class ConnectionSignal(BaseMusicCommandException):
    pass


@a.define(init=False)
class InvalidTimestampFormat(BaseMusicCommandException):
    pass


@a.define
class Forbidden(BaseMusicCommandException):
    perms: hkperms
    channel: t.Optional[hk.Snowflakeish] = a.field(default=None, kw_only=True)


@a.define
class Unautherized(Forbidden):
    pass


@a.define
class ChannelMoved(ConnectionSignal):
    old_channel: hk.Snowflakeish
    new_channel: hk.Snowflakeish
    to_stage: bool = a.field(factory=bool, kw_only=True)
    

@a.define
class RequestedToSpeak(ConnectionSignal):
    channel: hk.Snowflakeish


@a.define(init=False)
class PlaybackException(BaseMusicCommandException):
    pass


@a.define
class ConnectionException(PlaybackException):
    channel: hk.Snowflakeish


@a.define(init=False)
class NotConnected(PlaybackException):
    pass


@a.define
class NotYetSpeaker(ConnectionException):
    pass


@a.define(init=False)
class AlreadyConnected(ConnectionException):
    pass


@a.define(init=False)
class OthersInVoice(ConnectionException):
    pass


@a.define(init=False)
class OthersListening(OthersInVoice):
    pass


@a.define
class NotInVoice(BaseMusicCommandException):
    pass


@a.define(init=False)
class InternalError(PlaybackException):
    pass


@a.define
class PlaybackChangeRefused(PlaybackException):
    track: t.Optional[lv.TrackQueue] = None


@a.define(init=False)
class NotPlaying(PlaybackException):
    pass


@a.define(init=False)
class QueueEmpty(PlaybackException):
    pass


@a.define(init=False)
class TrackPaused(PlaybackException):
    pass


@a.define(init=False)
class TrackStopped(PlaybackException):
    pass


@a.define(init=False)
class QueryEmpty(BaseMusicCommandException):
    pass


@a.define(init=False)
class LyricsNotFound(BaseMusicCommandException):
    pass


@a.define(init=False)
class VotingTimeout(TimeoutError, BaseMusicCommandException):
    pass
