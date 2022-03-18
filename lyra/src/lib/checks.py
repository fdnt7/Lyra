import enum as e
import typing as t

import hikari as hk
import tanjun as tj
import lavasnek_rs as lv

from .utils import (
    Contextish,
    get_client,
    get_pref,
    get_rest,
    fetch_permissions,
    err_reply,
)
from .errors import (
    AlreadyConnected,
    NotYetSpeaker,
    OthersInVoice,
    PlaybackChangeRefused,
    TrackStopped,
    NotConnected,
    Unautherized,
    NotPlaying,
    QueueEmpty,
    TrackPaused,
    OthersListening,
    QueryEmpty,
    VotingTimeout,
)
from .extras import NULL, format_flags
from hikari.permissions import Permissions as hkperms


DJ_PERMS: t.Final = hkperms.DEAFEN_MEMBERS | hkperms.MUTE_MEMBERS
MOVER_PERMS: t.Final = hkperms.MOVE_MEMBERS | DJ_PERMS

ConnectionInfo = dict[str, t.Any]


class Checks(e.Flag):
    CATCH_ALL = 0

    IN_VC = e.auto()
    """Checks whether you are in voice or whether you have the permissions specified"""

    OTHERS_NOT_IN_VC = e.auto()
    """Checks whether there is no one else in voice or whether you have the premissions specified"""

    IN_VC_ALONE = IN_VC | OTHERS_NOT_IN_VC
    """Checks whether you are alone in voice or whether you have the permissions specified"""

    CONN = e.auto()
    """Check whether the bot is currently connected in this guild's voice"""

    QUEUE = e.auto()
    """Check whether the queue for this guild is not yet empty"""

    SPEAK = e.auto()
    """Check whether the bot is a speaker if it's in a stage channel"""

    PLAYING = e.auto()
    """Check whether there is a currently playing track"""

    CAN_SEEK_ANY = e.auto()
    """Checks whether your requested track is currently playing or you have the DJ permissions"""

    ALONE__SPEAK__CAN_SEEK_ANY = SPEAK | CAN_SEEK_ANY | IN_VC_ALONE
    """Checks whether the bot is speaking and you are alone in voice or whether you have the permissions specified, then checks whether your requested track is currently playing or you have the DJ permissions"""

    NP_YOURS = e.auto()
    """Checks whether you requested the current track or you have the DJ permissions"""

    ALONE__SPEAK__NP_YOURS = SPEAK | NP_YOURS | IN_VC_ALONE
    """Checks whether the bot is speaking and you are alone in voice or whether you have the permissions specified, then checks whether you requested the current track or you have the DJ permissions"""

    ADVANCE = STOP = e.auto()
    """Check whether the current track had been stopped"""

    PLAYBACK = PAUSE = e.auto()
    """Checks whether the currently playing track had been paused"""


async def check_speaker(ctx_: Contextish, /):
    assert ctx_.guild_id

    client = get_client(ctx_)
    assert client.cache

    bot_u = client.cache.get_me()
    assert bot_u

    state = client.cache.get_voice_state(ctx_.guild_id, bot_u.id)
    assert state
    if (
        (vc_id := state.channel_id)
        and isinstance(client.cache.get_guild_channel(vc_id), hk.GuildStageChannel)
        and state.user_id == bot_u.id
        and state.is_suppressed
    ):
        raise NotYetSpeaker(vc_id)


async def check_others_not_in_vc__(
    ctx_: Contextish, conn: ConnectionInfo, /, *, perms: hkperms = MOVER_PERMS
):
    auth_perms = await fetch_permissions(ctx_)
    member = ctx_.member
    client = get_client(ctx_)
    assert client.cache and ctx_.guild_id and member
    channel = conn['channel_id']

    voice_states = client.cache.get_voice_states_view_for_channel(
        ctx_.guild_id, channel
    )
    others_in_voice = set(
        filter(
            lambda v: not v.member.is_bot and v.member.id != member.id,
            voice_states.values(),
        )
    )

    if not (auth_perms & (perms | hkperms.ADMINISTRATOR)) and others_in_voice:
        raise OthersInVoice(channel)


async def check_others_not_in_vc(ctx_: Contextish, lvc: lv.Lavalink, /):
    assert ctx_.guild_id

    conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
    assert isinstance(conn, dict)
    await check_others_not_in_vc__(ctx_, conn, perms=DJ_PERMS)


def check(
    checks: Checks = Checks.CATCH_ALL,
    /,
    *,
    perms: hkperms = hkperms.NONE,
    vote: bool = False,
):
    from .lavaimpl import get_queue
    from .music import init_listeners_voting
    from .extras import VoidCoroutine

    dj_perms_fmt = format_flags(DJ_PERMS)
    mover_perms_fmt = format_flags(MOVER_PERMS)

    P = t.ParamSpec('P')

    async def check_in_vc__(
        ctx_: Contextish, conn: ConnectionInfo, /, *, perms: hkperms = DJ_PERMS
    ):
        member = ctx_.member
        assert member and ctx_.guild_id

        client = get_client(ctx_)
        assert client.cache
        auth_perms = await fetch_permissions(ctx_)

        channel: int = conn['channel_id']
        voice_states = client.cache.get_voice_states_view_for_channel(
            ctx_.guild_id, channel
        )
        author_in_voice = set(
            filter(
                lambda v: v.member.id == member.id,
                voice_states.values(),
            )
        )

        if not (auth_perms & (perms | hkperms.ADMINISTRATOR)) and not author_in_voice:
            raise AlreadyConnected(channel)

    async def check_in_vc(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.guild_id

        conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
        assert isinstance(conn, dict)
        await check_in_vc__(ctx_, conn)

    async def check_np_yours(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.member

        auth_perms = await fetch_permissions(ctx_)
        q = await get_queue(ctx_, lvc)
        assert q.current is not None
        if ctx_.member.id != q.current.requester and not auth_perms & (
            DJ_PERMS | hkperms.ADMINISTRATOR
        ):
            raise PlaybackChangeRefused(q.current)

    async def check_can_seek_any(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.member

        auth_perms = await fetch_permissions(ctx_)
        if not (auth_perms & (DJ_PERMS | hkperms.ADMINISTRATOR)):
            if not (np := (await get_queue(ctx_, lvc)).current):
                raise Unautherized(DJ_PERMS)
            if ctx_.member.id != np.requester:
                raise PlaybackChangeRefused(np)

    async def check_stop(ctx_: Contextish, lvc: lv.Lavalink):
        if (await get_queue(ctx_, lvc)).is_stopped:
            raise TrackStopped

    async def check_conn(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.guild_id

        conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
        if not conn:
            raise NotConnected

    async def check_queue(ctx_: Contextish, lvc: lv.Lavalink):
        if not await get_queue(ctx_, lvc):
            raise QueueEmpty

    async def check_playing(ctx_: Contextish, lvc: lv.Lavalink):
        if not (await get_queue(ctx_, lvc)).current:
            raise NotPlaying

    async def check_pause(ctx_: Contextish, lvc: lv.Lavalink):
        if (await get_queue(ctx_, lvc)).is_paused:
            raise TrackPaused

    def callback(func: t.Callable[P, VoidCoroutine]) -> t.Callable[P, VoidCoroutine]:
        async def inner(*args: P.args, **kwargs: P.kwargs) -> None:

            ctx_ = next((a for a in args if isinstance(a, Contextish)), NULL)
            lvc = next((a for a in kwargs.values() if isinstance(a, lv.Lavalink)), NULL)

            assert ctx_, "Missing a Contextish object"
            assert ctx_.guild_id
            p = get_pref(ctx_)

            try:
                if perms:
                    auth_perms = await fetch_permissions(ctx_)
                    if not (auth_perms & (perms | hkperms.ADMINISTRATOR)):
                        raise Unautherized(perms)

                if not lvc:
                    await func(*args, **kwargs)
                    return

                if Checks.CONN & checks:
                    await check_conn(ctx_, lvc)
                if Checks.QUEUE & checks:
                    await check_queue(ctx_, lvc)
                if Checks.SPEAK & checks:
                    await check_speaker(ctx_)
                if Checks.PLAYING & checks:
                    await check_playing(ctx_, lvc)
                if Checks.IN_VC & checks:
                    await check_in_vc(ctx_, lvc)
                if Checks.OTHERS_NOT_IN_VC & checks:
                    try:
                        await check_others_not_in_vc(ctx_, lvc)
                    except OthersInVoice as exc:
                        try:
                            if Checks.CAN_SEEK_ANY & checks:
                                await check_can_seek_any(ctx_, lvc)
                            if Checks.NP_YOURS & checks:
                                await check_np_yours(ctx_, lvc)
                            if not (Checks.NP_YOURS | Checks.CAN_SEEK_ANY) & checks:
                                raise OthersListening(exc.channel) from exc
                        except (
                            OthersListening,
                            PlaybackChangeRefused,
                            Unautherized,
                        ) as exc_:
                            if vote:
                                assert isinstance(ctx_, tj.abc.Context)
                                try:
                                    await init_listeners_voting(ctx_, lvc)
                                except VotingTimeout:
                                    raise exc_
                            else:
                                raise

                if Checks.STOP & checks:
                    await check_stop(ctx_, lvc)
                if Checks.PAUSE & checks:
                    await check_pause(ctx_, lvc)

                await func(*args, **kwargs)
            except Unautherized as exc:
                await err_reply(
                    ctx_,
                    content=f"🚫 You lack the `{format_flags(exc.perms)}` permissions to use this command",
                )
            except OthersListening as exc:
                await err_reply(
                    ctx_,
                    content=f"🚫 You can only do this if you are alone in <#{exc.channel}>.\n **You bypass this by having the {dj_perms_fmt} permissions**",
                )
            except OthersInVoice as exc:
                await err_reply(
                    ctx_,
                    content=f"🚫 Someone else is already in <#{exc.channel}>.\n **You bypass this by having the {mover_perms_fmt} permissions**",
                )
            except AlreadyConnected as exc:
                await err_reply(
                    ctx_,
                    content=f"🚫 Join <#{exc.channel}> first. **You bypass this by having the {dj_perms_fmt} permissions**",
                )
            except NotConnected:
                await err_reply(
                    ctx_,
                    content=f"❌ Not currently connected to any channel. Use `{p}join` or `{p}play` first",
                )
            except QueueEmpty:
                await err_reply(ctx_, content="❗ The queue is empty")
            except NotYetSpeaker as exc:
                rest = get_rest(ctx_)
                await err_reply(
                    ctx_,
                    content="❗👥 Not yet a speaker in the current stage. Sending a request to speak...",
                )
                await rest.edit_my_voice_state(
                    ctx_.guild_id, exc.channel, request_to_speak=True
                )
            except NotPlaying:
                await err_reply(ctx_, content="❗ Nothing is playing at the moment")
            except PlaybackChangeRefused:
                await err_reply(
                    ctx_,
                    content=f"🚫 You are not the current song requester\n**You bypass this by having the {dj_perms_fmt} permissions**",
                )
            except TrackPaused:
                await err_reply(ctx_, content="❗ The current track is paused")
            except TrackStopped:
                await err_reply(
                    ctx_,
                    content=f"❗ The current track had been stopped. Use `{p}skip`, `{p}restart` or `{p}remove` the current track first",
                )
            except QueryEmpty:
                await err_reply(
                    ctx_, content="❓ No tracks found. Please try changing your wording"
                )

        return inner

    return callback
