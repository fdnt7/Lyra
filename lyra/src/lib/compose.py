import asyncio
import typing as t
import functools as ft

import tanjun as tj
import lavasnek_rs as lv

from hikari.permissions import Permissions as hkperms

from .expects import BindErrorExpects, CheckErrorExpects
from .utils import (
    BindSig,
    BaseCommandType,
    Contextish,
    get_client,
    fetch_permissions,
    init_confirmation_prompt,
)
from .flags import (
    Binds,
    Checks,
    DJ_PERMS,
    ConnectionInfo,
    others_not_in_vc_check_impl,
    parse_binds,
    parse_checks,
    speaker_check,
)
from .errors import (
    AlreadyConnected,
    BaseLyraException,
    CommandCancelled,
    OthersInVoice,
    PlaybackChangeRefused,
    TrackStopped,
    NotConnected,
    Unauthorized,
    NotPlaying,
    QueueEmpty,
    TrackPaused,
    OthersListening,
    VotingTimeout,
)
from .extras import NULL, Decorator, Option, Result, Panic
from .lavautils import get_queue


async def others_not_in_vc_check(ctx_: Contextish, lvc: lv.Lavalink, /) -> Result[bool]:
    assert ctx_.guild_id

    conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
    assert isinstance(conn, dict)
    return await others_not_in_vc_check_impl(ctx_, conn, perms=DJ_PERMS)


#


def with_cb_check(
    checks: Checks = Checks.CATCH_ALL,
    /,
    *,
    perms: hkperms = hkperms.NONE,
    vote: bool = False,
    prompt: bool = False,
):
    from .extras import VoidCoro
    from .musicutils import init_listeners_voting

    P = t.ParamSpec('P')

    async def _check_in_vc(
        ctx_: Contextish, conn: ConnectionInfo, /, *, perms: hkperms = DJ_PERMS
    ):
        member = ctx_.member
        assert ctx_.guild_id

        client = get_client(ctx_)
        assert client.cache
        auth_perms = await fetch_permissions(ctx_)

        channel: int = conn['channel_id']
        voice_states = client.cache.get_voice_states_view_for_channel(
            ctx_.guild_id, channel
        )
        author_in_voice = {
            *filter(
                lambda v: member and v.member.id == member.id,
                voice_states.values(),
            )
        }

        if not (auth_perms & (perms | hkperms.ADMINISTRATOR)) and not author_in_voice:
            raise AlreadyConnected(channel)

    async def check_in_vc(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.guild_id

        conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
        assert isinstance(conn, dict)
        await _check_in_vc(ctx_, conn)

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
                raise Unauthorized(DJ_PERMS)
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

    def callback(func: t.Callable[P, VoidCoro]) -> t.Callable[P, VoidCoro]:
        @ft.wraps(func)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> None:

            ctx_ = next((a for a in args if isinstance(a, Contextish)), NULL)

            assert ctx_, "Missing a Contextish object"
            assert ctx_.guild_id
            client = get_client(ctx_)

            lvc = client.get_type_dependency(lv.Lavalink)
            inj_func = tj.as_self_injecting(client)(func)

            try:
                if perms:
                    auth_perms = await fetch_permissions(ctx_)
                    if not (auth_perms & (perms | hkperms.ADMINISTRATOR)):
                        raise Unauthorized(perms)
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
                            Unauthorized,
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

                if prompt:
                    assert isinstance(ctx_, tj.abc.Context)
                    try:
                        await init_confirmation_prompt(ctx_)
                    except CommandCancelled | asyncio.TimeoutError as exc:
                        await BindErrorExpects(ctx_).expect(exc)
                        return
                await inj_func(*args, **kwargs)
            except BaseLyraException as exc:
                await CheckErrorExpects(ctx_).expect(exc)

        return inner

    return callback


_CMD = t.TypeVar('_CMD', bound=BaseCommandType)


async def _as_author_permission_check(
    ctx: tj.abc.Context, perms: hkperms | int
) -> Panic[bool]:
    assert perms
    check = tj.checks.AuthorPermissionCheck(perms, error_message=None)
    if not await check(ctx):
        await CheckErrorExpects(ctx).expect_unauthorized(Unauthorized(hkperms(perms)))
        raise tj.HaltExecution
    return True


def with_cmd_composer(
    binds: Option[Binds] = None,
    checks: Option[Checks] = None,
    *,
    perms: Option[hkperms] = None,
) -> Decorator[_CMD]:

    _checks: list[tj.abc.CheckSig] = []
    _binds: list[BindSig] = []

    if binds:
        _binds.extend(parse_binds(binds))

    if checks:
        _checks.extend(parse_checks(checks))

    if perms:
        _checks.insert(0, ft.partial(_as_author_permission_check, perms=perms))

    def _with_checks_and_binds(cmd: _CMD, /) -> _CMD:
        cmd.metadata['checks'] = checks
        cmd.metadata['binds'] = binds
        cmd.metadata['perms'] = perms
        return tj.with_all_checks(*_binds, *_checks)(cmd)

    return _with_checks_and_binds


def with_cmd_checks(checks: Checks, /) -> Decorator[_CMD]:
    """Bind an implementation of tanjun's "all check" to a command from the given check flags through a decorator call



    Args
    ---
        checks (`Checks`): The check flags

    Returns
    ---
        `t.Callable[[_CMD], _CMD]`: The bound command for method chaining
    """

    _checks = parse_checks(checks)

    def _with_checks(cmd: _CMD, /) -> _CMD:
        cmd.metadata['checks'] = checks
        return tj.with_all_checks(*_checks)(cmd)

    return _with_checks


def with_author_permission_check(permissions: hkperms | int, /) -> Decorator[_CMD]:
    def _with_author_permission_check(cmd: _CMD, /) -> _CMD:
        cmd.metadata['perms'] = permissions
        return cmd.add_check(ft.partial(_as_author_permission_check, perms=permissions))

    return _with_author_permission_check


with_developer_permission_check = with_cmd_checks(Checks.DEVELOPER)
