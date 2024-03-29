import typing as t
import asyncio

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from ..consts import TIMEOUT, __developers__
from ..extras import AutoDocsFlag, Fallible, Option, Panic
from ..errors import (
    NotDeveloperError,
    NotYetSpeakerError,
    AlreadyConnectedError,
    OthersInVoiceError,
    OthersListeningError,
    PlaybackChangeRefused,
    UnauthorizedError,
    VotingTimeoutError,
    CommandCancelledError,
    NotInVoiceError,
    RequestedToSpeak,
    CheckErrorExpects,
    BindErrorExpects,
)
from ..utils import (
    DJ_PERMS,
    BindSig,
    ContextishType,
    ConnectionInfo,
    delete_after,
    fetch_permissions,
    get_client,
    start_confirmation_prompt,
)
from ..lava import get_queue
from ..music import start_listeners_voting


class Checks(AutoDocsFlag):
    CATCH_ALL = """Checks nothing, but catches every command-related exceptions""", 0

    IN_VC = """Checks whether you are in voice or whether you have the DJ permissions"""

    OTHERS_NOT_IN_VC = """Checks whether there is no one else in voice or whether you have the DJ permissions"""

    CONN = """Checks whether the bot is currently connected in this guild's voice"""

    QUEUE = """Checks whether the queue for this guild is not yet empty"""

    SPEAK = """Checks whether the bot is a speaker if it's in a stage channel"""

    PLAYING = """Checks whether there is a currently playing track"""

    CAN_SEEK_ANY = """Checks whether your requested track is currently playing or you have the DJ permissions"""

    NP_YOURS = """Checks whether you requested the current track or you have the DJ permissions"""

    ADVANCE = """Check whether the current track had been stopped"""

    PLAYBACK = PAUSE = """Checks whether the currently playing track had been paused"""

    DEVELOPER = """Checks whether the command user is a developer"""


IN_VC_ALONE = Checks.IN_VC | Checks.OTHERS_NOT_IN_VC
"""Checks whether you are alone in voice or whether you have the permissions specified"""

ALONE__SPEAK__CAN_SEEK_ANY = Checks.SPEAK | Checks.CAN_SEEK_ANY | IN_VC_ALONE
"""Checks whether the bot is speaking and you are alone in voice or whether you have the permissions specified, then checks whether your requested track is currently playing or you have the DJ permissions"""

ALONE__SPEAK__NP_YOURS = Checks.SPEAK | Checks.NP_YOURS | IN_VC_ALONE
"""Checks whether the bot is speaking and you are alone in voice or whether you have the permissions specified, then checks whether you requested the current track or you have the DJ permissions"""


class Binds(AutoDocsFlag):
    NONE = """Binds nothing""", 0
    CONNECT_VC = """Binds an auto voice channel connection on command pre-execution"""
    CONFIRM = """Binds a confirmation prompting on command pre-execution"""
    VOTE = """Binds a voting prompt to be used when needed"""


async def speaker_check(ctx_: ContextishType, /) -> Fallible[bool]:
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
        raise NotYetSpeakerError(vc_id)
    return True


async def developer_check(ctx: tj.abc.Context, /) -> Fallible[bool]:
    if int(ctx.author.id) not in __developers__:
        raise NotDeveloperError
    return True


async def as_developer_check(ctx: tj.abc.Context, /) -> Panic[bool]:
    try:
        return await developer_check(ctx)
    except NotDeveloperError:
        await CheckErrorExpects(ctx).expect_not_developer()
    raise tj.HaltExecution


def parse_checks(checks: Checks, /) -> tuple[tj.abc.CheckSig, ...]:
    _checks: list[tj.abc.CheckSig] = []

    async def _as_conn_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        assert ctx.guild_id

        conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
        if not conn:
            await CheckErrorExpects(ctx).expect_not_connected()
            raise tj.HaltExecution
        return True

    async def _as_queue_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        if not await get_queue(ctx, lvc):
            await CheckErrorExpects(ctx).expect_queue_empty()
            raise tj.HaltExecution
        return True

    async def _as_speaker_check(ctx: tj.abc.Context, /) -> Panic[bool]:
        try:
            return await speaker_check(ctx)
        except NotYetSpeakerError as exc:
            await CheckErrorExpects(ctx).expect_not_yet_speaker(exc)
        raise tj.HaltExecution

    async def _as_playing_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        if not (await get_queue(ctx, lvc)).current:
            await CheckErrorExpects(ctx).expect_not_playing()
            raise tj.HaltExecution
        return True

    async def __check_in_vc(
        ctx: tj.abc.Context,
        conn: ConnectionInfo,
        /,
        *,
        perms: hk.Permissions = DJ_PERMS,
    ) -> Fallible[bool]:
        member = ctx.member
        assert ctx.guild_id

        client = get_client(ctx)
        assert client.cache and member
        auth_perms = await fetch_permissions(ctx)

        channel: int = conn['channel_id']
        voice_states = client.cache.get_voice_states_view_for_channel(
            ctx.guild_id, channel
        )
        author_in_voice = frozenset(
            filter(lambda v: v.member.id == member.id, voice_states.values())
        )

        if (
            not (auth_perms & (perms | hk.Permissions.ADMINISTRATOR))
            and not author_in_voice
        ):
            raise AlreadyConnectedError(channel)
        return True

    async def _as_in_vc_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        assert ctx.guild_id

        conn = t.cast(
            Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx.guild_id)
        )
        assert conn is not None
        try:
            return await __check_in_vc(ctx, conn)
        except AlreadyConnectedError as exc:
            await CheckErrorExpects(ctx).expect_already_connected(exc)
        raise tj.HaltExecution

    async def ___as_np_yours_check(
        ctx: tj.abc.Context, /, *, lvc: lv.Lavalink
    ) -> Fallible[bool]:
        assert ctx.member

        auth_perms = await fetch_permissions(ctx)
        q = await get_queue(ctx, lvc)
        assert q.current is not None
        if ctx.member.id != q.current.requester and not auth_perms & (
            DJ_PERMS | hk.Permissions.ADMINISTRATOR
        ):
            raise PlaybackChangeRefused(q.current)
        return True

    async def ___as_can_seek_any_check(
        ctx: tj.abc.Context, /, *, lvc: lv.Lavalink
    ) -> Fallible[bool]:
        assert ctx.member

        auth_perms = await fetch_permissions(ctx)
        if not (auth_perms & (DJ_PERMS | hk.Permissions.ADMINISTRATOR)):
            if not (np := (await get_queue(ctx, lvc)).current):
                raise UnauthorizedError(DJ_PERMS)
            if ctx.member.id != np.requester:
                raise PlaybackChangeRefused(np)
        return True

    async def ___handles_voting(
        ctx: tj.abc.Context,
        exc_: OthersListeningError | PlaybackChangeRefused | UnauthorizedError,
        /,
        *,
        lvc: lv.Lavalink,
    ) -> Fallible[bool]:
        if (cmd := ctx.command) and Binds.VOTE in cmd.metadata.get('binds', set()):
            try:
                await start_listeners_voting(ctx, lvc)
            except VotingTimeoutError:
                raise exc_
            else:
                return True
        else:
            raise

    async def __handles_advanced_case(
        ctx: tj.abc.Context, exc: OthersInVoiceError, /, *, lvc: lv.Lavalink
    ) -> Panic[bool]:
        try:
            assert checks
            if Checks.CAN_SEEK_ANY & checks:
                return await ___as_can_seek_any_check(ctx, lvc=lvc)
            if Checks.NP_YOURS & checks:
                return await ___as_np_yours_check(ctx, lvc=lvc)
            if not (Checks.NP_YOURS | Checks.CAN_SEEK_ANY) & checks:
                raise OthersListeningError(exc.channel) from exc
            return True
        except (
            OthersListeningError,
            PlaybackChangeRefused,
            UnauthorizedError,
        ) as exc_:
            try:
                return await ___handles_voting(ctx, exc_, lvc=lvc)
            except (
                OthersListeningError,
                PlaybackChangeRefused,
                UnauthorizedError,
            ) as _exc:
                await CheckErrorExpects(ctx).expect(_exc)
            raise tj.HaltExecution

    async def _as_others_not_in_vc_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        from ..connections import others_not_in_vc_check_impl

        assert ctx.guild_id

        conn = t.cast(
            Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx.guild_id)
        )
        assert conn is not None
        try:
            return await others_not_in_vc_check_impl(ctx, conn, perms=DJ_PERMS)
        except OthersInVoiceError as exc:
            return await __handles_advanced_case(ctx, exc, lvc=lvc)

    async def _as_stop_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        if (await get_queue(ctx, lvc)).is_stopped:
            await CheckErrorExpects(ctx).expect_track_stopped()
            raise tj.HaltExecution
        return True

    async def _as_pause_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        if (await get_queue(ctx, lvc)).is_paused:
            await CheckErrorExpects(ctx).expect_track_paused()
            raise tj.HaltExecution
        return True

    if Checks.DEVELOPER & checks:
        _checks.append(as_developer_check)
    if Checks.CONN & checks:
        _checks.append(_as_conn_check)
    if Checks.QUEUE & checks:
        _checks.append(_as_queue_check)
    if Checks.SPEAK & checks:
        _checks.append(_as_speaker_check)
    if Checks.PLAYING & checks:
        _checks.append(_as_playing_check)
    if Checks.IN_VC & checks:
        _checks.append(_as_in_vc_check)
    if Checks.OTHERS_NOT_IN_VC & checks:
        _checks.append(_as_others_not_in_vc_check)
    if Checks.ADVANCE & checks:
        _checks.append(_as_stop_check)
    if Checks.PAUSE & checks:
        _checks.append(_as_pause_check)

    return (*_checks,)


def parse_binds(binds: Binds, /) -> tuple[BindSig, ...]:
    _binds: list[BindSig] = []

    async def _as_confirm_bind(ctx: tj.abc.Context, /) -> Panic[bool]:
        try:
            await start_confirmation_prompt(ctx)
        except (CommandCancelledError, asyncio.TimeoutError) as exc:
            await BindErrorExpects(ctx).expect(exc)
            raise tj.HaltExecution
        return True

    async def __wait_until_speaker(
        ctx: tj.abc.Context, sig: RequestedToSpeak, /
    ) -> Panic[bool]:
        bot = ctx.client.get_type_dependency(hk.GatewayBot)
        assert not isinstance(bot, al.abc.Undefined)

        if isinstance(ctx, tj.abc.AppCommandContext):
            await ctx.defer()

        wait_msg = await ctx.rest.create_message(
            ctx.channel_id,
            f"⏳🎭📎 <#{sig.channel}> `(Sent a request to speak. Waiting to become a speaker...)`",
        )

        bot_u = bot.get_me()

        try:
            await bot.wait_for(
                hk.VoiceStateUpdateEvent,
                timeout=TIMEOUT // 2,
                predicate=lambda e: bool(bot_u and e.state.user_id == bot_u.id)
                and bool(e.state.channel_id)
                and not e.state.is_suppressed
                and bool(
                    ctx.cache
                    and isinstance(
                        ctx.cache.get_guild_channel(sig.channel),
                        hk.GuildStageChannel,
                    )
                ),
            )
        except asyncio.TimeoutError:
            await wait_msg.edit(
                "⌛ Waiting timed out. Please invite the bot to speak and reinvoke the command",
            )
            asyncio.create_task(delete_after(ctx, wait_msg, time=5.0))
            raise tj.HaltExecution
        else:
            return True

    async def _as_connect_vc(
        ctx: tj.abc.Context, /, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        from ..connections import join_impl_precaught

        assert ctx.guild_id

        ch = ctx.get_channel()
        assert ch

        conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
        if conn:
            return True
        async with ch.trigger_typing():
            try:
                vc = await join_impl_precaught(ctx, lvc)
            except RequestedToSpeak as sig:
                return await __wait_until_speaker(ctx, sig)
            except NotInVoiceError:
                await BindErrorExpects(ctx).expect_not_in_voice()
                raise tj.HaltExecution
            else:
                return bool(vc)

    if Binds.CONFIRM & binds:
        _binds.append(_as_confirm_bind)
    if Binds.CONNECT_VC & binds:
        _binds.append(_as_connect_vc)
    if Binds.VOTE & binds:
        ...

    return (*_binds,)
