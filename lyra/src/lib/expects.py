import abc
import typing as t
import asyncio

import attr as a
import lavasnek_rs as lv

from .utils import Contextish, dj_perms_fmt, err_say, get_pref, get_rest, say
from .extras import Result, VoidCoro, format_flags
from .errors import (
    CommandCancelled,
    ErrorNotRecognized,
    InternalError,
    NotInVoice,
    PlaybackChangeRefused,
    Unauthorized,
    OthersListening,
    OthersInVoice,
    AlreadyConnected,
    NotConnected,
    QueueEmpty,
    NotYetSpeaker,
    NotPlaying,
    TrackPaused,
    QueryEmpty,
    TrackStopped,
    NoPlayableTracks,
    NotDeveloper,
)


@a.frozen
class BaseErrorExpects(abc.ABC):
    context: Contextish

    @abc.abstractmethod
    def match_expect(self, error: Exception, /) -> Result[t.Callable[[], VoidCoro]]:
        ...

    @abc.abstractmethod
    async def expect(self, error: Exception, /) -> bool:
        expect = self.match_expect(error)
        try:
            await expect()
        except ErrorNotRecognized:
            return False
        return True


@a.frozen
class CheckErrorExpects(BaseErrorExpects):
    context: Contextish

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

    async def expect_unauthorized(self, error: Unauthorized, /):
        await err_say(
            self.context,
            content=f"🚫 You lack the `{format_flags(error.perms)}` permissions to use this command",
        )

    async def expect_others_listening(self, error: OthersListening, /):
        await err_say(
            self.context,
            content=f"🚫 You can only do this if you are alone in <#{error.channel}>.\n **You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_others_in_voice(self, error: OthersInVoice, /):
        await err_say(
            self.context,
            content=f"🚫 Someone else is already in <#{error.channel}>.\n **You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_already_connected(self, error: AlreadyConnected, /):
        await err_say(
            self.context,
            content=f"🚫 Join <#{error.channel}> first. **You bypass this by having the {dj_perms_fmt} permissions**",
        )

    async def expect_not_connected(self):
        p = get_pref(ctx := self.context)
        await err_say(
            ctx,
            content=f"❌ Not currently connected to any channel. Use `{p}join` or `{p}play` first",
        )

    async def expect_queue_empty(self):
        await err_say(self.context, content="❗ The queue is empty")

    async def expect_not_yet_speaker(self, error: NotYetSpeaker, /):
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
        p = get_pref(ctx := self.context)
        await err_say(
            ctx,
            content=f"❗ The current track had been stopped. Use `{p}skip`, `{p}restart` or `{p}remove` the current track first",
        )

    async def expect_query_empty(self, error: QueryEmpty, /):
        await err_say(
            self.context, content=f"❓ No tracks found for `{error.query_str}`"
        )

    async def expect_no_playable_tracks(self):
        await err_say(self.context, content="💔 Cannot play any given track(s)")

    async def expect_not_developer(self):
        await err_say(self.context, content="🚫⚙️ Reserved for bot's developers only")

    def match_expect(self, error: Exception, /) -> Result[t.Callable[[], VoidCoro]]:
        match error:
            case lv.NetworkError():
                return lambda: self.expect_network_error()
            case lv.NoSessionPresent() | InternalError():
                return lambda: self.expect_internal_error()
            case PlaybackChangeRefused():
                return lambda: self.expect_playback_change_refused()
            case Unauthorized():
                return lambda: self.expect_unauthorized(error)
            case OthersListening():
                return lambda: self.expect_others_listening(error)
            case OthersInVoice():
                return lambda: self.expect_others_in_voice(error)
            case AlreadyConnected():
                return lambda: self.expect_already_connected(error)
            case NotConnected():
                return lambda: self.expect_not_connected()
            case QueueEmpty():
                return lambda: self.expect_queue_empty()
            case NotYetSpeaker():
                return lambda: self.expect_not_yet_speaker(error)
            case NotPlaying():
                return lambda: self.expect_not_playing()
            case TrackPaused():
                return lambda: self.expect_track_paused()
            case TrackStopped():
                return lambda: self.expect_track_stopped()
            case QueryEmpty():
                return lambda: self.expect_query_empty(error)
            case NoPlayableTracks():
                return lambda: self.expect_no_playable_tracks()
            case NotDeveloper():
                return lambda: self.expect_not_developer()
            case _:
                raise ErrorNotRecognized

    async def expect(self, error: Exception, /) -> bool:
        return await super().expect(error)


@a.frozen
class BindErrorExpects(BaseErrorExpects):
    context: Contextish

    async def expect_command_cancelled(self):
        await err_say(self.context, follow_up=False, content="🛑 Cancelled the command")

    async def expect_timeout_error(self):
        await say(
            self.context,
            content="⌛ Timed out. Please reinvoke the command",
        )

    async def expect_not_in_voice(self):
        p = get_pref(ctx := self.context)
        await err_say(
            ctx,
            content=f"❌ Please join a voice channel first. You can also do `{p}join channel:` `[🔊 ...]`",
        )

    def match_expect(self, error: Exception, /) -> Result[t.Callable[[], VoidCoro]]:
        match error:
            case NotInVoice():
                return lambda: self.expect_not_in_voice()
            case CommandCancelled():
                return lambda: self.expect_command_cancelled()
            case asyncio.TimeoutError():
                return lambda: self.expect_timeout_error()
            case _:
                raise ErrorNotRecognized

    async def expect(self, error: Exception, /) -> bool:
        return await super().expect(error)
