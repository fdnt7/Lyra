import abc
import typing as t

import attr as a
import hikari as hk
import lavasnek_rs as lv

from ..extras import Option


@a.frozen
class Argument:
    got: t.Any
    expected: t.Any


@a.frozen(init=False)
class BaseLyraError(abc.ABC, Exception):
    pass


@a.frozen(init=False)
class BaseLyraSignal(abc.ABC, Exception):
    pass


@a.frozen(init=False)
class ConnectionSignal(BaseLyraSignal):
    pass


@a.frozen
class ChannelMoved(ConnectionSignal):
    old_channel: hk.Snowflakeish
    new_channel: hk.Snowflakeish
    to_stage: bool = a.field(factory=bool, kw_only=True)


@a.frozen
class RequestedToSpeak(ConnectionSignal):
    channel: hk.Snowflakeish


@a.frozen
class BadArgument(BaseLyraError):
    arg: Argument


@a.frozen(init=False)
class InvalidArgumentError(BadArgument):
    pass


@a.frozen(init=False)
class IllegalArgumentError(BadArgument):
    pass


@a.frozen(init=False)
class InvalidTimestampFormat(BaseLyraError):
    pass


@a.frozen
class ForbiddenError(BaseLyraError):
    perms: hk.Permissions
    channel: Option[hk.Snowflakeish] = a.field(default=None, kw_only=True)


@a.frozen
class RestrictedError(BaseLyraError):
    mode: t.Literal[1, -1]
    obj: t.Any


@a.frozen
class UnauthorizedError(ForbiddenError):
    pass


@a.frozen(init=False)
class NotDeveloperError(BaseLyraError):
    pass


@a.frozen(init=False)
class PlaybackException(BaseLyraError):
    pass


@a.frozen
class ConnectionException(PlaybackException):
    channel: hk.Snowflakeish


@a.frozen(init=False)
class NotConnectedError(PlaybackException):
    pass


@a.frozen
class NotYetSpeakerError(ConnectionException):
    pass


@a.frozen(init=False)
class AlreadyConnectedError(ConnectionException):
    pass


@a.frozen(init=False)
class OthersInVoiceError(ConnectionException):
    pass


@a.frozen(init=False)
class OthersListeningError(OthersInVoiceError):
    pass


@a.frozen(init=False)
class NotInVoiceError(BaseLyraError):
    pass


@a.frozen(init=False)
class InternalError(PlaybackException):
    pass


@a.frozen
class PlaybackChangeRefused(PlaybackException):
    track: Option[lv.TrackQueue] = None


@a.frozen(init=False)
class NotPlayingError(PlaybackException):
    pass


@a.frozen(init=False)
class QueueEmptyError(PlaybackException):
    pass


@a.frozen(init=False)
class TrackPausedError(PlaybackException):
    pass


@a.frozen(init=False)
class TrackStoppedError(PlaybackException):
    pass


@a.frozen
class QueryEmptyError(BaseLyraError):
    query_str: str


@a.frozen(init=False)
class LyricsNotFoundError(BaseLyraError):
    pass


@a.frozen(init=False)
class NoPlayableTracksError(BaseLyraError):
    pass


@a.frozen(init=False)
class VotingTimeoutError(TimeoutError, BaseLyraError):
    pass


@a.frozen(init=False)
class ErrorNotRecognizedError(NotImplementedError, BaseLyraError):
    pass


@a.frozen(init=False)
class CommandCancelledError(BaseLyraError):
    pass
