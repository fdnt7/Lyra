import abc
import typing as t

import attr as a
import hikari as hk
import lavasnek_rs as lv


from hikari.permissions import Permissions as hkperms


@a.define
class Argument:
    got: t.Any
    expected: t.Any


@a.define(init=False)
class BaseCommandException(abc.ABC, Exception):
    pass


@a.define
class BadArgument(BaseCommandException):
    arg: Argument


@a.define(init=False)
class InvalidArgument(BadArgument):
    pass


@a.define(init=False)
class IllegalArgument(BadArgument):
    pass


@a.define(init=False)
class ConnectionSignal(BaseCommandException):
    pass


@a.define(init=False)
class InvalidTimestampFormat(BaseCommandException):
    pass


@a.define
class Forbidden(BaseCommandException):
    perms: hkperms
    channel: t.Optional[hk.Snowflakeish] = a.field(default=None, kw_only=True)


@a.define
class Restricted(BaseCommandException):
    mode: t.Literal[1, -1]
    obj: t.Any


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
class PlaybackException(BaseCommandException):
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
class NotInVoice(BaseCommandException):
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
class QueryEmpty(BaseCommandException):
    pass


@a.define(init=False)
class LyricsNotFound(BaseCommandException):
    pass


@a.define(init=False)
class VotingTimeout(TimeoutError, BaseCommandException):
    pass
