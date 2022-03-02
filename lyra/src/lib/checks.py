from .utils import *


DJ_PERMS = hkperms.DEAFEN_MEMBERS | hkperms.MUTE_MEMBERS


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

    PLAYING = e.auto()
    """Check whether there is a currently playing track"""

    CAN_PLAY_AT = e.auto()
    """Checks whether your requested track is currently playing or you have the DJ permissions"""

    ALONE_OR_CAN_SEEK_QUEUE = CAN_PLAY_AT | IN_VC_ALONE
    """Checks whether you are alone in voice or whether you have the permissions specified, then checks whether your requested track is currently playing or you have the DJ permissions"""

    CURR_T_YOURS = e.auto()
    """Checks whether you requested the current track or you have the DJ permissions"""

    ALONE_OR_CURR_T_YOURS = CURR_T_YOURS | IN_VC_ALONE
    """Checks whether you are alone in voice or whether you have the permissions specified, then checks whether you requested the current track or you have the DJ permissions"""

    ADVANCE = STOP = e.auto()
    """Check whether the current track had been stopped"""

    PLAYBACK = PAUSE = e.auto()
    """Checks whether the currently playing track had been paused"""


async def check_others_not_in_vc__(ctx_: Contextish, perms: hkperms, conn: dict):
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


async def check_others_not_in_vc(ctx_: Contextish, lvc: lv.Lavalink):
    assert ctx_.guild_id

    conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
    assert isinstance(conn, dict)
    await check_others_not_in_vc__(ctx_, DJ_PERMS, conn)


def check(
    checks: Checks = Checks.CATCH_ALL,
    /,
    *,
    perms: hkperms = hkperms.NONE,
    vote: bool = False,
):
    from .lavaimpl import get_queue
    from .music import init_listeners_voting
    from .utils import VoidCoroutine

    P = t.ParamSpec('P')

    async def check_auth_in_vc__(ctx_: Contextish, perms: hkperms, conn: dict):
        member = ctx_.member
        assert member and ctx_.guild_id

        client = get_client(ctx_)
        assert client.cache
        auth_perms = await fetch_permissions(ctx_)

        channel = conn['channel_id']
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
            raise NotInVoice(channel)

    async def check_in_vc(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.guild_id

        conn = lvc.get_guild_gateway_connection_info(ctx_.guild_id)
        assert isinstance(conn, dict)
        await check_auth_in_vc__(ctx_, DJ_PERMS, conn)

    async def check_curr_t_yours(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.member

        auth_perms = await fetch_permissions(ctx_)
        q = await get_queue(ctx_, lvc)
        assert q.current is not None
        if ctx_.member.id != q.current.requester and not auth_perms & (
            DJ_PERMS | hkperms.ADMINISTRATOR
        ):
            raise PlaybackChangeRefused(q.current)

    async def check_can_play_at(ctx_: Contextish, lvc: lv.Lavalink):
        assert ctx_.member

        auth_perms = await fetch_permissions(ctx_)
        if not (auth_perms & (DJ_PERMS | hkperms.ADMINISTRATOR)):
            if not (np := (await get_queue(ctx_, lvc)).current):
                raise Forbidden(DJ_PERMS)
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

            ctx = next((a for a in args if isinstance(a, Contextish)), None)
            bot = next(
                (a for a in kwargs.values() if isinstance(a, hk.GatewayBot)), None
            )
            lvc = next((a for a in kwargs.values() if isinstance(a, lv.Lavalink)), None)

            assert ctx
            p = get_pref(ctx)

            try:
                if perms:
                    auth_perms = await fetch_permissions(ctx)
                    if not (auth_perms & (perms | hkperms.ADMINISTRATOR)):
                        raise Forbidden(perms)

                if not lvc:
                    await func(*args, **kwargs)
                    return

                if Checks.CONN & checks:
                    await check_conn(ctx, lvc)
                if Checks.QUEUE & checks:
                    await check_queue(ctx, lvc)
                if Checks.PLAYING & checks:
                    await check_playing(ctx, lvc)
                if Checks.IN_VC & checks:
                    await check_in_vc(ctx, lvc)
                if Checks.OTHERS_NOT_IN_VC & checks:
                    try:
                        await check_others_not_in_vc(ctx, lvc)
                    except OthersInVoice as exc:
                        try:
                            if Checks.CAN_PLAY_AT & checks:
                                await check_can_play_at(ctx, lvc)
                            if Checks.CURR_T_YOURS & checks:
                                await check_curr_t_yours(ctx, lvc)
                            if not (Checks.CURR_T_YOURS | Checks.CAN_PLAY_AT) & checks:
                                raise OthersListening(exc.channel) from exc
                        except (
                            OthersListening,
                            PlaybackChangeRefused,
                            Forbidden,
                        ) as exc_:
                            if vote:
                                assert bot and isinstance(ctx, tj.abc.Context)
                                try:
                                    await init_listeners_voting(ctx, bot, lvc)
                                except VotingTimeout:
                                    raise exc_
                            else:
                                raise

                if Checks.STOP & checks:
                    await check_stop(ctx, lvc)
                if Checks.PAUSE & checks:
                    await check_pause(ctx, lvc)

                await func(*args, **kwargs)
            except Forbidden as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 You lack the `{format_flags(exc.perms)}` permissions to use this command",
                )
            except OthersListening as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 You can only do this if you are alone in <#{exc.channel}>.\n **You bypass this by having the `Deafen` & `Mute Members` permissions**",
                )
            except OthersInVoice as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 Someone else is already in <#{exc.channel}>.\n **You bypass this by having the `Move Members` permissions**",
                )
            except NotInVoice as exc:
                await err_reply(
                    ctx,
                    content=f"🚫 Join <#{exc.channel}> first. **You bypass this by having the `Deafen` & `Mute Members` permissions**",
                )
            except NotConnected:
                await err_reply(
                    ctx,
                    content=f"❌ Not currently connected to any channel. Use `{p}join` or `{p}play` first",
                )
            except QueueEmpty:
                await err_reply(ctx, content="❗ The queue is empty")
            except NotPlaying:
                await err_reply(ctx, content="❗ Nothing is playing at the moment")
            except PlaybackChangeRefused:
                await err_reply(
                    ctx,
                    content=f"🚫 This can only be done by the current song requester\n**You bypass this by having the `Deafen` & `Mute Members` permissions**",
                )
            except TrackPaused:
                await err_reply(ctx, content="❗ The current track is paused")
            except TrackStopped:
                await err_reply(
                    ctx,
                    content=f"❗ The current track had been stopped. Use `{p}skip`, `{p}restart` or `{p}remove` the current track first",
                )
            except QueryEmpty:
                await err_reply(
                    ctx, content="❓ No tracks found. Please try changing your wording"
                )

        return inner

    return callback
