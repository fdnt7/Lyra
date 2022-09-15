import typing as t
import asyncio

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from hikari.permissions import Permissions as hkperms

from ..utils import (
    DJ_PERMS,
    TIMEOUT,
    BindSig,
    Contextish,
    ConnectionInfo,
    delete_after,
    fetch_permissions,
    get_client,
    start_confirmation_prompt,
)
from ..errors import (
    AlreadyConnected,
    CommandCancelled,
    NotDeveloper,
    NotInVoice,
    NotYetSpeaker,
    OthersInVoice,
    OthersListening,
    PlaybackChangeRefused,
    RequestedToSpeak,
    Unauthorized,
    VotingTimeout,
)
from ..errors.expects import BindErrorExpects, CheckErrorExpects
from ..extras import AutoDocsFlag, Result, Option, Panic
from ..lava.utils import get_queue
from ..connections import others_not_in_vc_check_impl


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


async def speaker_check(ctx_: Contextish, /) -> Result[bool]:
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
    return True


async def developer_check(ctx: tj.abc.Context, /) -> Result[bool]:
    from .. import consts as c

    if int(ctx.author.id) not in c.__developers__:
        raise NotDeveloper
    return True


async def as_developer_check(ctx: tj.abc.Context, /) -> Panic[bool]:
    try:
        return await developer_check(ctx)
    except NotDeveloper:
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
        except NotYetSpeaker as exc:
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
        ctx: tj.abc.Context, conn: ConnectionInfo, /, *, perms: hkperms = DJ_PERMS
    ) -> Result[bool]:
        member = ctx.member
        assert ctx.guild_id

        client = get_client(ctx)
        assert client.cache and member
        auth_perms = await fetch_permissions(ctx)

        channel: int = conn['channel_id']
        voice_states = client.cache.get_voice_states_view_for_channel(
            ctx.guild_id, channel
        )

        author_in_voice = (
            await voice_states.iterator()
            .filter(lambda v: v.member.id == member.id)
            .collect(frozenset)
        )

        if not (auth_perms & (perms | hkperms.ADMINISTRATOR)) and not author_in_voice:
            raise AlreadyConnected(channel)
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
        except AlreadyConnected as exc:
            await CheckErrorExpects(ctx).expect_already_connected(exc)
        raise tj.HaltExecution

    async def ___as_np_yours_check(
        ctx: tj.abc.Context, /, *, lvc: lv.Lavalink
    ) -> Result[bool]:
        assert ctx.member

        auth_perms = await fetch_permissions(ctx)
        q = await get_queue(ctx, lvc)
        assert q.current is not None
        if ctx.member.id != q.current.requester and not auth_perms & (
            DJ_PERMS | hkperms.ADMINISTRATOR
        ):
            raise PlaybackChangeRefused(q.current)
        return True

    async def ___as_can_seek_any_check(
        ctx: tj.abc.Context, /, *, lvc: lv.Lavalink
    ) -> Result[bool]:
        assert ctx.member

        auth_perms = await fetch_permissions(ctx)
        if not (auth_perms & (DJ_PERMS | hkperms.ADMINISTRATOR)):
            if not (np := (await get_queue(ctx, lvc)).current):
                raise Unauthorized(DJ_PERMS)
            if ctx.member.id != np.requester:
                raise PlaybackChangeRefused(np)
        return True

    async def ___handles_voting(
        ctx: tj.abc.Context,
        exc_: OthersListening | PlaybackChangeRefused | Unauthorized,
        /,
        *,
        lvc: lv.Lavalink,
    ) -> Result[bool]:
        if (cmd := ctx.command) and Binds.VOTE in cmd.metadata.get('binds', set()):
            try:
                from ..musicutils import start_listeners_voting

                await start_listeners_voting(ctx, lvc)
            except VotingTimeout:
                raise exc_
            else:
                return True
        else:
            raise

    async def __handles_advanced_case(
        ctx: tj.abc.Context, exc: OthersInVoice, /, *, lvc: lv.Lavalink
    ) -> Panic[bool]:
        try:
            assert checks
            if Checks.CAN_SEEK_ANY & checks:
                return await ___as_can_seek_any_check(ctx, lvc=lvc)
            if Checks.NP_YOURS & checks:
                return await ___as_np_yours_check(ctx, lvc=lvc)
            if not (Checks.NP_YOURS | Checks.CAN_SEEK_ANY) & checks:
                raise OthersListening(exc.channel) from exc
            return True
        except (
            OthersListening,
            PlaybackChangeRefused,
            Unauthorized,
        ) as exc_:
            try:
                return await ___handles_voting(ctx, exc_, lvc=lvc)
            except (OthersListening, PlaybackChangeRefused, Unauthorized) as _exc:
                await CheckErrorExpects(ctx).expect(_exc)
            raise tj.HaltExecution

    async def _as_others_not_in_vc_check(
        ctx: tj.abc.Context, /, *, lvc: al.Injected[lv.Lavalink]
    ) -> Panic[bool]:
        assert ctx.guild_id

        conn = t.cast(
            Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx.guild_id)
        )
        assert conn is not None
        try:
            return await others_not_in_vc_check_impl(ctx, conn, perms=DJ_PERMS)
        except OthersInVoice as exc:
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
        except (CommandCancelled, asyncio.TimeoutError) as exc:
            await BindErrorExpects(ctx).expect(exc)
            raise tj.HaltExecution
        return True

    async def __wait_until_speaker(
        ctx: tj.abc.Context, sig: RequestedToSpeak, /
    ) -> Panic[bool]:
        bot = ctx.client.get_type_dependency(hk.GatewayBot)
        assert bot

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

    async def _as_connect_vc(ctx: tj.abc.Context, /) -> Panic[bool]:
        assert ctx.guild_id

        ch = ctx.get_channel()
        lvc = ctx.client.get_type_dependency(lv.Lavalink)
        assert lvc and ch

        conn = lvc.get_guild_gateway_connection_info(ctx.guild_id)
        if conn:
            return True
        async with ch.trigger_typing():
            try:
                from ..connections import join_impl_precaught

                vc = await join_impl_precaught(ctx, lvc)
            except RequestedToSpeak as sig:
                return await __wait_until_speaker(ctx, sig)
            except NotInVoice:
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
