import abc
import typing as t
import asyncio

import attr as a
import lavasnek_rs as lv

if t.TYPE_CHECKING:
    from ..extras import Fallible
from ..utils import ContextishType, dj_perms_fmt, err_say, get_rest, say
from ..cmd import CommandIdentifier, get_full_cmd_repr_from_identifier
from .errors import (
    CommandCancelledError,
    ErrorNotRecognizedError,
    InternalError,
    NotInVoiceError,
    PlaybackChangeRefused,
    UnauthorizedError,
    OthersListeningError,
    OthersInVoiceError,
    AlreadyConnectedError,
    NotConnectedError,
    QueueEmptyError,
    NotYetSpeakerError,
    NotPlayingError,
    TrackPausedError,
    QueryEmptyError,
    TrackStoppedError,
    NoPlayableTracksError,
    NotDeveloperError,
)


ExpectSig = t.Callable[[], t.Awaitable[None]]


@a.frozen
class BaseErrorExpects(abc.ABC):
    context: ContextishType

    @abc.abstractmethod
    def match_expect(self, error: Exception, /) -> 'Fallible[ExpectSig]':
        ...

    @abc.abstractmethod
    async def expect(self, error: Exception, /) -> bool:
        expect = self.match_expect(error)
        try:
            await expect()
        except ErrorNotRecognizedError:
            return False
        return True


@a.frozen
class CheckErrorExpects(BaseErrorExpects):
    context: ContextishType

    async def expect_network_error(self):
        await err_say(self.context, content="⁉️ A network error has occurred")

    async def expect_internal_error(self):
        await err_say(
            self.context,
            content="😦 Something internal went wrong. Please try again in few minutes",
        )

    async def expect_playback_change_refused(self):
        await err_say(
            self.context,
            content=f"🚫 You are not the current song requester\n**You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_unauthorized(self, error: UnauthorizedError, /):
        from ..extras import format_flags

        await err_say(
            self.context,
            content=f"🚫 You lack the `{format_flags(error.perms)}` permissions to use this command",
        )

    async def expect_others_listening(self, error: OthersListeningError, /):
        await err_say(
            self.context,
            content=f"🚫 You can only do this if you are alone in <#{error.channel}>.\n **You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_others_in_voice(self, error: OthersInVoiceError, /):
        await err_say(
            self.context,
            content=f"🚫 Someone else is already in <#{error.channel}>.\n **You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_already_connected(self, error: AlreadyConnectedError, /):
        await err_say(
            self.context,
            content=f"🚫 Join <#{error.channel}> first. **You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_not_connected(self):
        join_r = get_full_cmd_repr_from_identifier(
            CommandIdentifier.JOIN, ctx := self.context
        )
        play_r = get_full_cmd_repr_from_identifier(CommandIdentifier.PLAY, ctx)

        await err_say(
            ctx,
            content=f"❌ Not currently connected to any channel. Use {join_r} or {play_r} first",
        )

    async def expect_queue_empty(self):
        await err_say(self.context, content="❗ The queue is empty")

    async def expect_not_yet_speaker(self, error: NotYetSpeakerError, /):
        rest = get_rest(ctx := self.context)
        await err_say(
            ctx,
            content=f"❗👥 Not yet a speaker in the stage <#{error.channel}>. Please accept the newly sent speak request and reinvoke this command",
        )
        assert ctx.guild_id
        await rest.edit_my_voice_state(
            ctx.guild_id, error.channel, request_to_speak=True
        )

    async def expect_not_playing(self):
        await err_say(self.context, content="❗ Nothing is playing at the moment")

    async def expect_track_paused(self):
        await err_say(self.context, content="❗ The current track is paused")

    async def expect_track_stopped(self):
        skip_r = get_full_cmd_repr_from_identifier(
            CommandIdentifier.SKIP, ctx := self.context
        )
        restart_r = get_full_cmd_repr_from_identifier(CommandIdentifier.RESTART, ctx)
        remove_r = get_full_cmd_repr_from_identifier(CommandIdentifier.REMOVE, ctx)

        await err_say(
            ctx,
            content=f"❗ The current track had been stopped. Use {skip_r}, {restart_r} or {remove_r} for the current track first",
        )

    async def expect_query_empty(self, error: QueryEmptyError, /):
        await err_say(
            self.context, content=f"❓ No tracks found for `{error.query_str}`"
        )

    async def expect_no_playable_tracks(self):
        await err_say(self.context, content="💔 Cannot play any given track(s)")

    async def expect_not_developer(self):
        await err_say(self.context, content="🚫⚙️ Reserved for bot's developers only")

    def match_expect(self, error: Exception, /) -> 'Fallible[ExpectSig]':
        match error:
            case lv.NetworkError():
                return lambda: self.expect_network_error()
            case lv.NoSessionPresent() | InternalError():
                return lambda: self.expect_internal_error()
            case PlaybackChangeRefused():
                return lambda: self.expect_playback_change_refused()
            case UnauthorizedError():
                return lambda: self.expect_unauthorized(error)
            case OthersListeningError():
                return lambda: self.expect_others_listening(error)
            case OthersInVoiceError():
                return lambda: self.expect_others_in_voice(error)
            case AlreadyConnectedError():
                return lambda: self.expect_already_connected(error)
            case NotConnectedError():
                return lambda: self.expect_not_connected()
            case QueueEmptyError():
                return lambda: self.expect_queue_empty()
            case NotYetSpeakerError():
                return lambda: self.expect_not_yet_speaker(error)
            case NotPlayingError():
                return lambda: self.expect_not_playing()
            case TrackPausedError():
                return lambda: self.expect_track_paused()
            case TrackStoppedError():
                return lambda: self.expect_track_stopped()
            case QueryEmptyError():
                return lambda: self.expect_query_empty(error)
            case NoPlayableTracksError():
                return lambda: self.expect_no_playable_tracks()
            case NotDeveloperError():
                return lambda: self.expect_not_developer()
            case _:
                raise ErrorNotRecognizedError

    async def expect(self, error: Exception, /) -> bool:
        return await super().expect(error)


@a.frozen
class BindErrorExpects(BaseErrorExpects):
    context: ContextishType

    async def expect_command_cancelled(self):
        await err_say(self.context, follow_up=False, content="🛑 Cancelled the command")

    async def expect_timeout_error(self):
        await say(
            self.context,
            content="⌛ Timed out. Please reinvoke the command",
        )

    async def expect_not_in_voice(self):
        join_r = get_full_cmd_repr_from_identifier(
            CommandIdentifier.JOIN, ctx := self.context
        )
        await err_say(
            ctx,
            content=f"❌ Please join a voice channel first. You can also do {join_r} `channel:` `[🔊 ...]`",
        )

    def match_expect(self, error: Exception, /) -> 'Fallible[ExpectSig]':
        match error:
            case NotInVoiceError():
                return lambda: self.expect_not_in_voice()
            case CommandCancelledError():
                return lambda: self.expect_command_cancelled()
            case asyncio.TimeoutError():
                return lambda: self.expect_timeout_error()
            case _:
                raise ErrorNotRecognizedError

    async def expect(self, error: Exception, /) -> bool:
        return await super().expect(error)
