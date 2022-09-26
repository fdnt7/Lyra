import typing as t
import asyncio
import hashlib as hl
import functools as ft
import contextlib as ctxlib

import hikari as hk
import tanjun as tj
import alluka as al
from ..extras.types import AnyOr

import src.lib.globs as globs

from hikari.permissions import Permissions as hkperms
from hikari.messages import MessageFlag as msgflag

# pyright: reportUnusedImport=false
from .vars import RESTRICTOR, base_h, EmojiRefs, DJ_PERMS, dj_perms_fmt, guild_c
from .types import (
    ChannelAware,
    RESTAware,
    RESTAwareAware,
    ClientAware,
    ClientAwareGuildContextish,
    MaybeGuildIDAware,
    GuildContextish,
    IntCastable,
    AnyContextType,
    ContextishType,
    GuildAwareEventType,
    EditableComponentsType,
    # -
    ConnectionInfo,
    BindSig,
    ButtonBuilderType,
    MentionableType,
    JoinableChannelType,
    PartialMentionableType,
    RESTAwareType,
    with_annotated_args_wrapped,
)
from ..cmd import get_full_cmd_repr
from ..cmd.types import (
    GenericMenuCommandType,
    GenericMessageCommandGroupType,
    GenericMessageCommandType,
    GenericSlashCommandType,
)
from ..consts import TIMEOUT, Q_CHUNK
from ..errors import BaseLyraException, CommandCancelled
from ..extras import (
    Option,
    Result,
    Panic,
    URLstr,
    MapSig,
    DecorateSig,
    PredicateSig,
    join_and,
    limit_bytes_img_size,
    url_to_bytesio,
)
from ..dataimpl import LyraDBCollectionType


async def delete_after(
    ch_: ChannelAware,
    msg: hk.SnowflakeishOr[hk.PartialMessage],
    /,
    *,
    time: float = 3.5,
):
    await asyncio.sleep(time)
    ch = await ch_.fetch_channel()
    await ch.delete_messages(msg)


@t.overload
async def err_say(
    event: GuildAwareEventType,
    /,
    *,
    del_after: float = 3.5,
    channel: hk.Snowflakeish = ...,
    **kwargs: t.Any,
) -> Panic[hk.Message]:
    ...


@t.overload
async def err_say(
    ctx_: ContextishType,
    /,
    *,
    del_after: float = 3.5,
    follow_up: bool = True,
    ensure_result: t.Literal[False] = False,
    **kwargs: t.Any,
) -> Option[hk.Message]:
    ...


@t.overload
async def err_say(
    ctx_: ContextishType,
    /,
    *,
    del_after: float = 3.5,
    follow_up: bool = True,
    ensure_result: t.Literal[True] = True,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def err_say(
    g_r_inf: RESTAwareType,
    /,
    *,
    delete_after: float = 3.5,
    follow_up: bool = True,
    ensure_result: bool = False,
    channel: Option[hk.Snowflakeish] = None,
    **kwargs: t.Any,
) -> Option[hk.Message]:
    return await ft.partial(
        say,
        hidden=True,
        ensure_result=ensure_result,
        channel=channel,
        follow_up=follow_up,
        delete_after=delete_after,
    )(g_r_inf, **kwargs)


@t.overload
async def ephim_say(
    g_: GuildAwareEventType,
    /,
    *,
    channel: hk.Snowflakeish = ...,
    **kwargs: t.Any,
) -> Panic[hk.Message]:
    ...


@t.overload
async def ephim_say(
    ctx_: ContextishType,
    /,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def ephim_say(
    g_r_inf: RESTAwareType,
    /,
    *,
    channel: Option[hk.Snowflakeish] = None,
    **kwargs: t.Any,
) -> Option[hk.Message]:
    if isinstance(g_r_inf, hk.ComponentInteraction | tj.abc.AppCommandContext):
        return await say(g_r_inf, hidden=True, channel=channel, **kwargs)


@t.overload
async def say(
    g_: GuildAwareEventType,
    /,
    *,
    hidden: bool = False,
    channel: hk.Snowflakeish = ...,
    **kwargs: t.Any,
) -> Panic[hk.Message]:
    ...


@t.overload
async def say(
    ctx: tj.abc.Context,
    /,
    *,
    hidden: bool = False,
    follow_up: bool = False,
    ensure_result: t.Literal[False] = False,
    **kwargs: t.Any,
) -> Option[hk.Message]:
    ...


@t.overload
async def say(
    ctx: tj.abc.Context,
    /,
    *,
    hidden: bool = False,
    follow_up: bool = False,
    ensure_result: t.Literal[True] = True,
    **kwargs: t.Any,
) -> hk.Message:
    ...


@t.overload
async def say(
    inter: hk.ComponentInteraction,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[False] = False,
    show_author: bool = False,
    **kwargs: t.Any,
) -> Option[hk.Message]:
    ...


@t.overload
async def say(
    inter: hk.ComponentInteraction,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[True] = True,
    show_author: bool = False,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def say(
    g_r_inf: RESTAwareType,
    /,
    *,
    hidden: bool = False,
    follow_up: bool = False,
    ensure_result: bool = False,
    show_author: bool = False,
    channel: Option[hk.Snowflakeish] = None,
    **kwargs: t.Any,
):
    msg: Option[hk.Message] = None
    if kwargs.get('embed', hk.UNDEFINED) is hk.UNDEFINED:
        kwargs['embed'] = None
    if kwargs.get('components', hk.UNDEFINED) is hk.UNDEFINED:
        kwargs['components'] = ()

    try:
        if isinstance(g_r_inf, hk.ComponentInteraction | GuildAwareEventType):
            kwargs.pop('delete_after', None)

        flags = msgflag.EPHEMERAL if hidden else hk.UNDEFINED
        if isinstance(g_r_inf, GuildAwareEventType):
            if not channel:
                raise RuntimeError(
                    '`g_r_inf` was type `GuildInferableEvents` but `channel` was not passed'
                )
            msg = await g_r_inf.app.rest.create_message(channel, **kwargs)
        elif isinstance(g_r_inf, tj.abc.MessageContext):
            if g_r_inf.has_responded and not follow_up:
                msg = await g_r_inf.edit_last_response(**kwargs)
            else:
                msg = await g_r_inf.respond(**kwargs, reply=True)
        else:
            assert isinstance(
                g_r_inf, hk.ComponentInteraction | tj.abc.AppCommandContext
            )
            if isinstance(g_r_inf, tj.abc.AppCommandContext):
                if g_r_inf.has_responded:
                    if follow_up:
                        msg = await g_r_inf.create_followup(**kwargs, flags=flags)
                    else:
                        msg = await g_r_inf.edit_last_response(**kwargs)
                else:
                    msg = await g_r_inf.create_initial_response(**kwargs, flags=flags)
            else:
                assert isinstance(g_r_inf, hk.ComponentInteraction)
                if show_author and (cnt := kwargs.get('content')):
                    kwargs['content'] = f"{cnt} *(📨 __{g_r_inf.user.mention}__)*"
                msg = await g_r_inf.create_initial_response(
                    hk.ResponseType.MESSAGE_CREATE, **kwargs, flags=flags
                )
    except (RuntimeError, hk.NotFoundError):
        assert isinstance(g_r_inf, ContextishType)
        msg = await g_r_inf.edit_initial_response(**kwargs)
    finally:
        if not ensure_result:
            return msg
        if isinstance(g_r_inf, hk.ComponentInteraction):
            return (await g_r_inf.fetch_initial_response()) or msg
        if isinstance(g_r_inf, ContextishType):
            return (await g_r_inf.fetch_last_response()) or msg
        assert msg
        return msg


_EditableBuilderT = t.TypeVar(
    '_EditableBuilderT',
    bound=EditableComponentsType,
)


def disable_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    predicates: Option[PredicateSig[_EditableBuilderT]] = None,
) -> tuple[hk.api.ActionRowBuilder, ...]:
    edits: MapSig[_EditableBuilderT] = lambda x: x.set_is_disabled(True)
    reverts: MapSig[_EditableBuilderT] = lambda x: x.set_is_disabled(False)

    return edit_components(
        rest,
        *action_rows,
        edits=edits,
        reverts=reverts,
        predicates=predicates,
    )


_BuilderT = t.TypeVar(
    '_BuilderT',
    bound=hk.api.ComponentBuilder,
    contravariant=True,
)


def edit_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    edits: MapSig[_BuilderT],
    reverts: Option[MapSig[_BuilderT]] = None,
    predicates: Option[PredicateSig[_BuilderT]] = None,
) -> tuple[hk.api.ActionRowBuilder, ...]:
    reverts = reverts or (lambda _: _)
    predicates = predicates or (lambda _: True)

    action_rows_ = [*action_rows]
    for ar in action_rows_:
        components = ar.components
        ar = rest.build_action_row()
        for c in map(
            lambda c_: (
                # TODO: Find out why is pyright complaining at this line
                edits(c_)  # pyright: ignore [reportGeneralTypeIssues]
                if predicates(c_)  # pyright: ignore [reportGeneralTypeIssues]
                else reverts(c_)  # pyright: ignore [reportGeneralTypeIssues]
            ),
            components,
        ):
            ar.add_component(c)
    return (*action_rows_,)


@t.overload
def trigger_thinking(
    ctx: tj.abc.MessageContext,
    /,
    *,
    ephemeral: bool = False,
) -> hk.api.TypingIndicator:
    ...


@t.overload
def trigger_thinking(
    ctx: tj.abc.AppCommandContext,
    /,
    *,
    ephemeral: bool = False,
    flags: hk.UndefinedOr[int | msgflag] = hk.UNDEFINED,
) -> ctxlib._AsyncGeneratorContextManager[None]:  # pyright: ignore [reportPrivateUsage]
    ...


def trigger_thinking(
    ctx: AnyContextType,
    /,
    *,
    ephemeral: bool = False,
    flags: hk.UndefinedOr[int | msgflag] = hk.UNDEFINED,
):
    if isinstance(ctx, tj.abc.MessageContext) or ctx.has_responded:
        ch = t.cast(hk.TextableGuildChannel, ctx.get_channel())
        return ch.trigger_typing()

    @ctxlib.asynccontextmanager
    async def _defer():
        await ctx.defer(ephemeral=ephemeral, flags=flags)
        yield

    return _defer()


def extract_content(msg: hk.Message):
    return msg.content


async def start_confirmation_prompt(ctx: tj.abc.Context) -> Result[None]:
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert not isinstance(bot, al.abc.Undefined)

    cmd_r = get_full_cmd_repr(ctx)
    cmd = t.cast(
        GenericMessageCommandType | GenericSlashCommandType | GenericMenuCommandType,
        ctx.command,
    )

    callback = cmd.callback
    docs = callback.__doc__

    row = (
        ctx.rest.build_action_row()
        .add_button(hk.ButtonStyle.SUCCESS, 'prompt_y')
        .set_emoji('✔️')
        .add_to_container()
        .add_button(hk.ButtonStyle.DANGER, 'prompt_n')
        .set_emoji('✖️')
        .add_to_container()
    )
    embed = hk.Embed(
        title=f'⚠️ Confirmation prompt for command {cmd_r}',
        description="This will: __**%s**__\n\n" % docs if docs else None,
        color=0xDBDBDB,
    ).set_footer('Click the ✅ button below to proceed, or ❌ to cancel')

    msg = await say(ctx, ensure_result=True, embed=embed, components=(row,))
    event = await bot.wait_for(
        hk.InteractionCreateEvent,
        timeout=TIMEOUT // 5,
        predicate=lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.custom_id in {'prompt_y', 'prompt_n'}
        and e.interaction.message.id == msg.id
        and e.interaction.user.id == ctx.author.id,
    )

    inter = t.cast(hk.ComponentInteraction, event.interaction)
    await inter.create_initial_response(hk.ResponseType.DEFERRED_MESSAGE_UPDATE)
    if inter.custom_id != 'prompt_y':
        raise CommandCancelled


_P_mgT = t.ParamSpec('_P_mgT')


def with_message_command_group_template(func: t.Callable[_P_mgT, t.Awaitable[None]], /):
    @ft.wraps(func)
    async def inner(*args: _P_mgT.args, **kwargs: _P_mgT.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)
        assert ctx

        cmd = t.cast(GenericMessageCommandGroupType, ctx.command)
        cmd_r = get_full_cmd_repr(ctx, pretty=False)
        sub_cmds_n = map(lambda s: next(iter(s.names)), cmd.commands)
        valid_cmds = ', '.join(f"`{cmd_r} {sub_cmd_n} ...`" for sub_cmd_n in sub_cmds_n)
        await err_say(
            ctx,
            delete_after=6.5,
            content=f"❌ This is a command group. Use the following subcommands instead:\n{valid_cmds}",
        )

        await func(*args, **kwargs)

    return inner


async def restricts_c(
    ctx: tj.abc.Context, /, *, cfg: al.Injected[LyraDBCollectionType]
) -> bool:
    if not (ctx.guild_id and ctx.member):
        return True

    g_cfg = cfg.find_one({'id': str(ctx.guild_id)})
    assert g_cfg

    res_ch: dict[str, t.Any] = g_cfg.get('restricted_ch', {})
    res_r: dict[str, t.Any] = g_cfg.get('restricted_r', {})
    res_u: dict[str, t.Any] = g_cfg.get('restricted_u', {})

    ch_wl = res_ch.get('wl_mode', 0)
    r_wl = res_r.get('wl_mode', 0)
    u_wl = res_u.get('wl_mode', 0)

    res_ch_all: set[int] = {*(map(int, res_ch.setdefault('all', [])))}
    res_r_all: set[int] = {*(map(int, res_r.setdefault('all', [])))}
    res_u_all: set[int] = {*(map(int, res_u.setdefault('all', [])))}

    author_perms = await tj.permissions.fetch_permissions(
        ctx.client, ctx.member, channel=ctx.channel_id
    )

    if author_perms & (hkperms.ADMINISTRATOR | RESTRICTOR):
        return True

    if u_wl == 1:
        if not (cond := ctx.author.id in res_u_all):
            await ephim_say(ctx, content="🚷 You aren't user whitelisted to use the bot")
        return cond

    if u_wl == -1 and ctx.author.id in res_u_all:
        await ephim_say(ctx, content="🚷 You are user blacklisted from using the bot")
        return False

    if r_wl == 1:
        if not (cond := bool({*ctx.member.role_ids} & res_r_all)):
            await ephim_say(ctx, content="🚷 You aren't role whitelisted to use the bot")
        return cond

    if r_wl == -1 and {*ctx.member.role_ids} & res_r_all:
        await ephim_say(ctx, content="🚷 You are role blacklisted from using the bot")
        return False

    if ch_wl == 1:
        if not (cond := ctx.channel_id in res_ch_all):
            wl_ch_txt = join_and(('<#%i>' % ch for ch in res_ch_all), and_=' or ')
            await ephim_say(
                ctx,
                content=f"🚷 This channel isn't whitelisted to use the bot. Consider using the bot in {wl_ch_txt}"
                if wl_ch_txt
                else "⚠️ There are no whitelisted channels yet. Please consider contacting the moderators to resolve this.",
            )
        return cond

    if ch_wl == -1 and ctx.channel_id in res_ch_all:
        await ephim_say(
            ctx,
            content=f"🚷 This channel is blacklisted from using the bot. Refrain from using the bot in {join_and(('<#%i>' % ch for ch in res_ch_all), and_=' or ')}",
        )
        return False

    return True


@base_h.with_on_parser_error
async def on_parser_error(ctx: tj.abc.Context, error: tj.errors.ParserError) -> None:
    msg = f"❌ You've given an invalid input: `{error}` "

    if related_errs := error.errors if isinstance(error, tj.ConversionError) else None:
        err_msg = '\n'.join(
            f'Cause-{i}: {next(iter(e.args))}' for i, e in enumerate(related_errs, 1)
        )
        msg += f"```arm\n{err_msg}```"
    await err_say(
        ctx,
        content=msg,
        delete_after=3.5 if not related_errs else 6.5,
    )


@base_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    if isinstance(error, BaseLyraException):
        pass
    elif isinstance(error, hk.ForbiddenError):
        await say(ctx, content="⛔ Not sufficient permissions to execute the command.")
    else:
        # error_tb = f"\n```py\n{''.join(tb.format_exception(type(error), value=error, tb=error.__traceback__))}```"
        error_tb = '`%s`' % error

        await say(ctx, content=f"⁉️ An unhandled error occurred: {error_tb}")
        return False
    return True


@base_h.with_pre_execution
async def pre_execution(
    ctx: tj.abc.Context, cfg: al.Injected[LyraDBCollectionType]
) -> None:
    g_id = str(ctx.guild_id)
    flt = {'id': g_id}

    if _g_cfg := cfg.find_one(flt):
        g_cfg = _g_cfg
    else:
        cfg.insert_one(flt)
        g_cfg: dict[str, t.Any] = flt.copy()

    if not g_cfg.get('auto_hide_embeds', True) or not isinstance(
        ctx, tj.abc.MessageContext
    ):
        return

    assert ctx.guild_id and ctx.cache

    bot_u = ctx.cache.get_me()
    assert bot_u

    bot_m = ctx.cache.get_member(ctx.guild_id, bot_u)
    assert bot_m

    bot_perms = await tj.permissions.fetch_permissions(
        ctx.client, bot_m, channel=ctx.channel_id
    )
    if bot_perms & hkperms.MANAGE_MESSAGES:
        await ctx.message.edit(flags=msgflag.SUPPRESS_EMBEDS)


def infer_guild(g_r_inf: IntCastable | MaybeGuildIDAware, /) -> int:
    if isinstance(g_r_inf, MaybeGuildIDAware):
        assert g_r_inf.guild_id
        return g_r_inf.guild_id
    return int(g_r_inf)


async def fetch_permissions(
    ctx_: GuildContextish | ClientAwareGuildContextish, /
) -> hk.Permissions:
    if isinstance((m := ctx_.member), hk.InteractionMember):
        return m.permissions
    member = ctx_.member
    assert member
    return await tj.permissions.fetch_permissions(
        get_client(ctx_), member, channel=ctx_.channel_id
    )


def get_client(_c_inf: AnyOr[ClientAware] = None, /) -> tj.abc.Client:
    if isinstance(_c_inf, ClientAware):
        return _c_inf.client

    _c: tj.Client = (
        globs.client  # pyright: ignore [reportGeneralTypeIssues, reportUnknownMemberType]
    )
    return _c


def get_rest(g_r_inf: RESTAware | RESTAwareAware, /):
    if isinstance(g_r_inf, RESTAware):
        return g_r_inf.rest
    return g_r_inf.app.rest


def get_guild_upload_limit(guild: hk.Guild, /) -> int:
    match guild.premium_tier:
        case hk.GuildPremiumTier.NONE | 0 | hk.GuildPremiumTier.TIER_1 | 1:
            return 8 * 2**20
        case hk.GuildPremiumTier.TIER_2 | 2:
            return 50 * 2**20
        case hk.GuildPremiumTier.TIER_3 | 3:
            return 100 * 2**20
        case _:
            raise NotImplementedError


def limit_img_size_by_guild(
    img_url_b: URLstr | bytes,
    g_inf: IntCastable | MaybeGuildIDAware,
    /,
    cache: hk.api.Cache,
):
    if isinstance(img_url_b, str):
        img_url_b = url_to_bytesio(img_url_b).getvalue()
    guild = cache.get_guild(infer_guild(g_inf))
    assert guild
    return limit_bytes_img_size(img_url_b, get_guild_upload_limit(guild))


def color_hash_obj(any_: t.Any) -> hk.Color:
    _r = repr(any_)
    h = hl.sha256(_r.encode('ascii'))
    h_d = int(h.hexdigest(), 16)

    r = (h_d & 0xFF0000) >> 16
    g = (h_d & 0x00FF00) >> 8
    b = h_d & 0x0000FF

    return hk.Color.from_rgb(r, g, b)
