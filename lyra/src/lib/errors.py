import abc
import typing as t

import attr as a
import hikari as hk
import lavasnek_rs as lv

from hikari.permissions import Permissions as hkperms

from ._extras_types import Option


@a.frozen
class Argument:
    got: t.Any
    expected: t.Any


@a.frozen(init=False)
class BaseLyraException(abc.ABC, Exception):
    pass


@a.frozen
class BadArgument(BaseLyraException):
    arg: Argument


@a.frozen(init=False)
class InvalidArgument(BadArgument):
    pass


@a.frozen(init=False)
class IllegalArgument(BadArgument):
    pass


@a.frozen(init=False)
class ConnectionSignal(BaseLyraException):
    pass


@a.frozen(init=False)
class InvalidTimestampFormat(BaseLyraException):
    pass


@a.frozen
class Forbidden(BaseLyraException):
    perms: hkperms
    channel: Option[hk.Snowflakeish] = a.field(default=None, kw_only=True)


@a.frozen
class Restricted(BaseLyraException):
    mode: t.Literal[1, -1]
    obj: t.Any


@a.frozen
class Unautherized(Forbidden):
    pass


@a.frozen
class ChannelMoved(ConnectionSignal):
    old_channel: hk.Snowflakeish
    new_channel: hk.Snowflakeish
    to_stage: bool = a.field(factory=bool, kw_only=True)


@a.frozen
class RequestedToSpeak(ConnectionSignal):
    channel: hk.Snowflakeish


@a.frozen(init=False)
class PlaybackException(BaseLyraException):
    pass


@a.frozen
class ConnectionException(PlaybackException):
    channel: hk.Snowflakeish


@a.frozen(init=False)
class NotConnected(PlaybackException):
    pass


@a.frozen
class NotYetSpeaker(ConnectionException):
    pass


@a.frozen(init=False)
class AlreadyConnected(ConnectionException):
    pass


@a.frozen(init=False)
class OthersInVoice(ConnectionException):
    pass


@a.frozen(init=False)
class OthersListening(OthersInVoice):
    pass


@a.frozen(init=False)
class NotInVoice(BaseLyraException):
    pass


@a.frozen(init=False)
class InternalError(PlaybackException):
    pass


@a.frozen
class PlaybackChangeRefused(PlaybackException):
    track: Option[lv.TrackQueue] = None


@a.frozen(init=False)
class NotPlaying(PlaybackException):
    pass


@a.frozen(init=False)
class QueueEmpty(PlaybackException):
    pass


@a.frozen(init=False)
class TrackPaused(PlaybackException):
    pass


@a.frozen(init=False)
class TrackStopped(PlaybackException):
    pass


@a.frozen
class QueryEmpty(BaseLyraException):
    query_str: str


@a.frozen(init=False)
class LyricsNotFound(BaseLyraException):
    pass


@a.frozen(init=False)
class NoPlayableTracks(BaseLyraException):
    pass


@a.frozen(init=False)
class VotingTimeout(TimeoutError, BaseLyraException):
    pass
