import asyncio
import typing as t
import functools as ft

import hikari as hk
import tanjun as tj
import lavasnek_rs as lv

from ..extras import NULL, DecorateSig, ArgsDecorateSig, Option, Fallible, Panic
from ..errors import (
    AlreadyConnectedError,
    BaseLyraError,
    CommandCancelledError,
    OthersInVoiceError,
    PlaybackChangeRefused,
    TrackStoppedError,
    NotConnectedError,
    UnauthorizedError,
    NotPlayingError,
    QueueEmptyError,
    TrackPausedError,
    OthersListeningError,
    VotingTimeoutError,
    CheckErrorExpects,
    BindErrorExpects,
)
from ..utils import (
    BindSig,
    ContextishType,
    get_client,
    fetch_permissions,
    start_confirmation_prompt,
)
from ..lava import get_queue
from ..music import start_listeners_voting
from .types import GenericCommandType
from .ids import CommandIdentifier
from .flags import (
    Binds,
    Checks,
    DJ_PERMS,
    ConnectionInfo,
    parse_binds,
    parse_checks,
    speaker_check,
)


async def others_not_in_vc_check(
    ctx_: ContextishType, lvc: lv.Lavalink, /
) -> Fallible[bool]:
    from ..connections import others_not_in_vc_check_impl

    assert ctx_.guild_id

    conn = t.cast(
        Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx_.guild_id)
    )
    assert conn is not None
    return await others_not_in_vc_check_impl(ctx_, conn, perms=DJ_PERMS)


#


def with_cb_check(
    checks: Checks = Checks.CATCH_ALL,
    /,
    *,
    perms: hk.Permissions = hk.Permissions.NONE,
    vote: bool = False,
    prompt: bool = False,
):
    P = t.ParamSpec('P')

    async def _check_in_vc(
        ctx_: ContextishType,
        conn: ConnectionInfo,
        /,
        *,
        perms: hk.Permissions = DJ_PERMS,
    ):
        member = ctx_.member
        assert ctx_.guild_id

        client = get_client(ctx_)
        assert client.cache and member
        auth_perms = await fetch_permissions(ctx_)

        channel: int = conn['channel_id']
        voice_states = client.cache.get_voice_states_view_for_channel(
            ctx_.guild_id, channel
        )
        author_in_voice = frozenset(
            filter(lambda v: v.member.id == member.id, voice_states.values())
        )

        if (
            not (auth_perms & (perms | hk.Permissions.ADMINISTRATOR))
            and not author_in_voice
        ):
            raise AlreadyConnectedError(channel)

    async def check_in_vc(ctx_: ContextishType, lvc: lv.Lavalink):
        assert ctx_.guild_id

        conn = t.cast(
            Option[ConnectionInfo], lvc.get_guild_gateway_connection_info(ctx_.guild_id)
        )
        assert conn is not None
        await _check_in_vc(ctx_, conn)

    async def check_np_yours(ctx_: ContextishType, lvc: lv.Lavalink):
        assert ctx_.member

        auth_perms = await fetch_permissions(ctx_)
        q = await get_queue(ctx_, lvc)
        assert q.current is not None
        if ctx_.member.id != q.current.requester and not auth_perms & (
            DJ_PERMS | hk.Permissions.ADMINISTRATOR
        ):
            raise PlaybackChangeRefused(q.current)

    async def check_can_seek_any(ctx_: ContextishType, lvc: lv.Lavalink):
        assert ctx_.member

        auth_perms = await fetch_permissions(ctx_)
        if not (auth_perms & (DJ_PERMS | hk.Permissions.ADMINISTRATOR)):
            if not (np := (await get_queue(ctx_, lvc)).current):
                raise UnauthorizedError(DJ_PERMS)
            if ctx_.member.id != np.requester:
                raise PlaybackChangeRefused(np)

    async def check_stop(ctx_: ContextishType, lvc: lv.Lavalink):
        if (await get_queue(ctx_, lvc)).is_stopped:
            raise TrackStoppedError

    async def check_conn(ctx_: ContextishType, lvc: lv.Lavalink):
        assert ctx_.guild_id

        conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
        if not conn:
            raise NotConnectedError

    async def check_queue(ctx_: ContextishType, lvc: lv.Lavalink):
        if not await get_queue(ctx_, lvc):
            raise QueueEmptyError

    async def check_playing(ctx_: ContextishType, lvc: lv.Lavalink):
        if not (await get_queue(ctx_, lvc)).current:
            raise NotPlayingError

    async def check_pause(ctx_: ContextishType, lvc: lv.Lavalink):
        if (await get_queue(ctx_, lvc)).is_paused:
            raise TrackPausedError

    def callback(
        func: t.Callable[P, t.Awaitable[None]]
    ) -> t.Callable[P, t.Awaitable[None]]:
        @ft.wraps(func)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> None:

            ctx_ = next((a for a in args if isinstance(a, ContextishType)), NULL)

            assert ctx_, "Missing a Contextish object"
            assert ctx_.guild_id
            client = get_client(ctx_)

            lvc = client.get_type_dependency(lv.Lavalink)
            inj_func = tj.as_self_injecting(client)(func)

            try:
                if perms:
                    auth_perms = await fetch_permissions(ctx_)
                    if not (auth_perms & (perms | hk.Permissions.ADMINISTRATOR)):
                        raise UnauthorizedError(perms)
                if not lvc:
                    await inj_func(*args, **kwargs)
                    return

                if Checks.CONN & checks:
                    await check_conn(ctx_, lvc)
                if Checks.QUEUE & checks:
                    await check_queue(ctx_, lvc)
                if Checks.SPEAK & checks:
                    await speaker_check(ctx_)
                if Checks.PLAYING & checks:
                    await check_playing(ctx_, lvc)
                if Checks.IN_VC & checks:
                    await check_in_vc(ctx_, lvc)
                if Checks.OTHERS_NOT_IN_VC & checks:
                    try:
                        await others_not_in_vc_check(ctx_, lvc)
                    except OthersInVoiceError as exc:
                        try:
                            if Checks.CAN_SEEK_ANY & checks:
                                await check_can_seek_any(ctx_, lvc)
                            if Checks.NP_YOURS & checks:
                                await check_np_yours(ctx_, lvc)
                            if not (Checks.NP_YOURS | Checks.CAN_SEEK_ANY) & checks:
                                raise OthersListeningError(exc.channel) from exc
                        except (
                            OthersListeningError,
                            PlaybackChangeRefused,
                            UnauthorizedError,
                        ) as exc_:
                            if vote:
                                assert isinstance(ctx_, tj.abc.Context)
                                try:
                                    await start_listeners_voting(ctx_, lvc)
                                except VotingTimeoutError:
                                    raise exc_
                            else:
                                raise

                if Checks.ADVANCE & checks:
                    await check_stop(ctx_, lvc)
                if Checks.PAUSE & checks:
                    await check_pause(ctx_, lvc)

                if prompt:
                    assert isinstance(ctx_, tj.abc.Context)
                    try:
                        await start_confirmation_prompt(ctx_)
                    except (CommandCancelledError, asyncio.TimeoutError) as exc:
                        await BindErrorExpects(ctx_).expect(exc)
                        return
                await inj_func(*args, **kwargs)
            except BaseLyraError as exc:
                await CheckErrorExpects(ctx_).expect(exc)

        return inner

    return callback


_CMD = t.TypeVar('_CMD', bound=GenericCommandType)
CommandDecorateSig = ArgsDecorateSig[[CommandIdentifier], _CMD]
IdentifiedCommandDecorateSig = DecorateSig[_CMD]


async def _as_author_permission_check(
    ctx: tj.abc.Context, perms: hk.Permissions | int
) -> Panic[bool]:
    assert perms
    check = tj.checks.AuthorPermissionCheck(perms, error_message=None)
    if not await check(ctx):
        await CheckErrorExpects(ctx).expect_unauthorized(
            UnauthorizedError(hk.Permissions(perms))
        )
        raise tj.HaltExecution
    return True


def with_identifier(
    identifier: CommandIdentifier, /
) -> IdentifiedCommandDecorateSig[_CMD]:
    def __set_metadata(ctx: tj.abc.Context, /):
        cmd = ctx.command
        assert cmd

        cmd.metadata.setdefault('identifier', identifier)
        return True

    return tj.with_check(__set_metadata, follow_wrapped=True)


def with_cmd_composer(
    binds: Option[Binds] = None,
    checks: Option[Checks] = None,
    *,
    perms: Option[hk.Permissions] = None,
) -> CommandDecorateSig[_CMD]:

    _checks_binds: list[tj.abc.CheckSig | BindSig] = []

    if binds:
        _checks_binds.extend(parse_binds(binds))

    if checks:
        _checks_binds.extend(parse_checks(checks))

    if perms:
        _checks_binds.insert(0, ft.partial(_as_author_permission_check, perms=perms))

    def _with_checks_and_binds(
        identifier: CommandIdentifier, /
    ) -> IdentifiedCommandDecorateSig[_CMD]:
        def __set_metadata(ctx: tj.abc.Context, /):
            cmd = ctx.command
            assert cmd

            cmd.metadata.setdefault('checks', checks)
            cmd.metadata.setdefault('binds', binds)
            cmd.metadata.setdefault('perms', perms)
            cmd.metadata.setdefault('identifier', identifier)
            return True

        return tj.with_all_checks(__set_metadata, *_checks_binds, follow_wrapped=True)

    return _with_checks_and_binds


def with_cmd_checks(checks: Checks, /) -> CommandDecorateSig[_CMD]:
    _checks = parse_checks(checks)

    def _with_checks(
        identifier: CommandIdentifier, /
    ) -> IdentifiedCommandDecorateSig[_CMD]:
        def __set_metadata(ctx: tj.abc.Context, /):
            cmd = ctx.command
            assert cmd

            cmd.metadata.setdefault('checks', checks)
            cmd.metadata.setdefault('identifier', identifier)
            return True

        return tj.with_all_checks(__set_metadata, *_checks, follow_wrapped=True)

    return _with_checks


def with_author_permission_check(
    perms: hk.Permissions | int, /
) -> CommandDecorateSig[_CMD]:
    def _with_author_permission_check(
        identifier: CommandIdentifier, /
    ) -> IdentifiedCommandDecorateSig[_CMD]:
        def __set_metadata(ctx: tj.abc.Context, /):
            cmd = ctx.command
            assert cmd

            cmd.metadata.setdefault('perms', perms)
            cmd.metadata.setdefault('identifier', identifier)
            return True

        return tj.with_all_checks(
            __set_metadata,
            ft.partial(_as_author_permission_check, perms=perms),
            follow_wrapped=True,
        )

    return _with_author_permission_check


with_developer_permission_check = with_cmd_checks(Checks.DEVELOPER)
