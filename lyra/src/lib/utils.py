import typing as t
import asyncio
import contextlib as ctxlib

import hikari as hk
import tanjun as tj
import alluka as al


from hikari.messages import MessageFlag as msgflag
from .extras import VoidCoroutine


EitherContext = tj.abc.MessageContext | tj.abc.AppCommandContext
Contextish = tj.abc.Context | hk.ComponentInteraction
"""A union "Context-ish" type hint. Includes:
* `tanjun.abc.Context` - A proper Context data
* `hikari.ComponentInteraction` - A similarly structured data"""

GuildInferableEvents = hk.GuildEvent | hk.VoiceEvent
"""A union type hint of events that can infer its guild id. Includes:
* `hikari.GuildEvent`
* `hikari.VoiceEvent`"""

GuildOrInferable = Contextish | hk.Snowflakeish | GuildInferableEvents
"""A union type hint of objects that can infer its guild id, or is the id itself. Includes:
* `hikari.Snowflakeish`
* `Contextish`
* `GuildInferableEvents`"""

RESTInferable = Contextish | GuildInferableEvents
"""A union type hint of objects that can infer its `hikari.api.RESTClient` client. Includes:
* `Contextish`
* `GuildInferableEvents`"""

GuildOrRESTInferable = GuildOrInferable | RESTInferable
"""A union type hint of objects that can infer its `hikari.api.RESTClient` client, its guild id, or is the id itself. Includes:
* `GuildOrInferable`
* `RESTInferable`"""

ButtonBuilderType = hk.api.ButtonBuilder[hk.api.ActionRowBuilder]
SelectMenuBuilderType = hk.api.SelectMenuBuilder[hk.api.ActionRowBuilder]
EditableComponentsType = ButtonBuilderType | SelectMenuBuilderType

EmojiRefs = t.NewType('EmojiRefs', dict[str, hk.KnownCustomEmoji])
GuildConfig = t.NewType('GuildConfig', dict[str, dict[str, t.Any]])

base_h = tj.AnyHooks()
guild_c = tj.checks.GuildCheck(
    error_message="🙅 Commands can only be used in guild channels"
)


Q_DIV = 15


async def delete_after(
    ctx_: Contextish, msg: hk.SnowflakeishOr[hk.PartialMessage], /, *, time: float = 3.5
):
    await asyncio.sleep(time)
    ch = await ctx_.fetch_channel()
    await ch.delete_messages(msg)


@t.overload
async def err_reply(
    event: GuildInferableEvents | hk.Snowflakeish,
    /,
    *,
    del_after: float = 3.5,
    channel: hk.GuildTextChannel = ...,
    **kwargs: t.Any,
) -> hk.Message:
    ...


@t.overload
async def err_reply(
    ctx_: Contextish,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: t.Literal[False] = False,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    ...


@t.overload
async def err_reply(
    ctx_: Contextish,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: t.Literal[True] = True,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def err_reply(
    g_r_inf: GuildOrRESTInferable,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: bool = False,
    channel: t.Optional[hk.GuildTextChannel] = None,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    return await reply(g_r_inf, hidden=True, ensure_result=ensure_result, channel=channel, delete_after=del_after, **kwargs)  # type: ignore


@t.overload
async def reply(
    g_: GuildInferableEvents | hk.Snowflakeish,
    /,
    *,
    hidden: bool = False,
    channel: hk.GuildTextChannel = ...,
    **kwargs: t.Any,
) -> hk.Message:
    ...


@t.overload
async def reply(
    ctx: tj.abc.Context,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[False] = False,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    ...


@t.overload
async def reply(
    ctx: tj.abc.Context,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[True] = True,
    **kwargs: t.Any,
) -> hk.Message:
    ...


@t.overload
async def reply(
    inter: hk.ComponentInteraction,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[False] = False,
    show_author: bool = False,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    ...


@t.overload
async def reply(
    inter: hk.ComponentInteraction,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[True] = True,
    show_author: bool = False,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def reply(
    g_r_inf: GuildOrRESTInferable,
    /,
    *,
    hidden: bool = False,
    ensure_result: bool = False,
    show_author: bool = False,
    channel: t.Optional[hk.GuildTextChannel] = None,
    **kwargs: t.Any,
):
    msg: t.Optional[hk.Message] = None
    try:
        if isinstance(g_r_inf, hk.ComponentInteraction | GuildInferableEvents):
            kwargs.pop('delete_after', None)

        flags = msgflag.EPHEMERAL if hidden else hk.UNDEFINED
        if isinstance(g_r_inf, GuildInferableEvents):
            if not channel:
                raise ValueError(
                    '`g_r_inf` was type `GuildInferableEvents` but `channel` was not passed'
                )
            msg = await g_r_inf.app.rest.create_message(channel, **kwargs)
        elif isinstance(g_r_inf, tj.abc.MessageContext):
            msg = await g_r_inf.respond(**kwargs, reply=True)
        else:
            assert isinstance(
                g_r_inf, hk.ComponentInteraction | tj.abc.AppCommandContext
            )
            if isinstance(g_r_inf, tj.abc.AppCommandContext):
                if g_r_inf.has_responded:
                    msg = await g_r_inf.create_followup(**kwargs, flags=flags)
                else:
                    msg = await g_r_inf.create_initial_response(**kwargs, flags=flags)
            else:
                assert isinstance(g_r_inf, hk.ComponentInteraction)
                if show_author and (cnt := kwargs.get('content')):
                    kwargs['content'] = f"{cnt} *by {g_r_inf.user.mention}*"
                msg = await g_r_inf.create_initial_response(
                    hk.ResponseType.MESSAGE_CREATE, **kwargs, flags=flags
                )
    except (RuntimeError, hk.NotFoundError):
        assert isinstance(g_r_inf, Contextish)
        msg = await g_r_inf.edit_initial_response(**kwargs)
    finally:
        if not ensure_result:
            return msg
        if isinstance(g_r_inf, hk.ComponentInteraction):
            return (await g_r_inf.fetch_initial_response()) or msg
        if isinstance(g_r_inf, Contextish):
            return (await g_r_inf.fetch_last_response()) or msg
        assert msg
        return msg


_C_d = t.TypeVar(
    '_C_d',
    bound=EditableComponentsType,
)


def disable_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    predicates: t.Callable[[_C_d], bool] = lambda _: True,
) -> tuple[hk.api.ActionRowBuilder, ...]:
    edits: t.Callable[[_C_d], _C_d] = lambda x: x.set_is_disabled(True)
    reverts: t.Callable[[_C_d], _C_d] = lambda x: x.set_is_disabled(False)

    return edit_components(
        rest,
        *action_rows,
        edits=edits,
        reverts=reverts,
        predicates=predicates,
    )


_C = t.TypeVar(
    '_C',
    bound=hk.api.ComponentBuilder,
    contravariant=True,
)


def edit_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    edits: t.Callable[[_C], _C],
    reverts: t.Callable[[_C], _C] = lambda _: _,
    predicates: t.Callable[[_C], bool] = lambda _: True,
) -> tuple[hk.api.ActionRowBuilder]:
    action_rows_ = [*action_rows]
    for a in action_rows_:
        components = a.components
        a = rest.build_action_row()
        for c in map(
            lambda c_: (edits(c_) if predicates(c_) else reverts(c_)),
            components,
        ):
            a.add_component(c)
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
) -> ctxlib._AsyncGeneratorContextManager[None]:  # type: ignore
    ...


def trigger_thinking(
    ctx: EitherContext,
    /,
    *,
    ephemeral: bool = False,
    flags: hk.UndefinedOr[int | msgflag] = hk.UNDEFINED,
):
    if isinstance(ctx, tj.abc.MessageContext):
        ch = ctx.get_channel()
        assert ch
        return ch.trigger_typing()
    assert isinstance(ctx, tj.abc.AppCommandContext)

    @ctxlib.asynccontextmanager
    async def _defer():
        await ctx.defer(ephemeral=ephemeral, flags=flags)
        try:
            yield
        except:
            raise

    return _defer()


_P = t.ParamSpec('_P')


def with_message_command_group_template(func: t.Callable[_P, VoidCoroutine], /):
    async def inner(*args: _P.args, **kwargs: _P.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)
        assert ctx

        cmd = ctx.command
        assert isinstance(cmd, tj.abc.MessageCommandGroup)
        p = next(iter(ctx.client.prefixes))
        cmd_n = next(iter(cmd.names))
        sub_cmds_n = map(lambda s: next(iter(s.names)), cmd.commands)
        valid_cmds = ', '.join(
            f"`{p}{cmd_n} {sub_cmd_n} ...`" for sub_cmd_n in sub_cmds_n
        )
        await err_reply(
            ctx,
            content=f"❌ This is a command group. Use the following instead:\n{valid_cmds}",
        )

        await func(*args, **kwargs)

    return inner


P_ = t.ParamSpec('P_')


# def with_message_menu_template(func: t.Callable[P_, VoidCoroutine], /):
#     async def inner(*args: P_.args, **kwargs: P_.kwargs):
#         ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)
#         msg = next((a for a in args if isinstance(a, hk.Message)), None)
#         assert ctx and msg

#         if not msg.content:
#             await err_reply(ctx, content="❌ Cannot process an empty message")
#             return

#         await func(*args, **kwargs)

#     return inner


async def restricts_c(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]):
    assert ctx.guild_id and ctx.member

    g_cfg = cfg[str(ctx.guild_id)]
    if g_cfg.setdefault('whitelisted', False):
        return bool(
            ctx.channel_id in g_cfg['whitelist']['channels']
            and {*ctx.member.role_ids} & {*g_cfg['whitelist']['roles']}
            and ctx.author.id in g_cfg['whitelist']['users']
        )
    else:
        if ctx.channel_id in g_cfg['blacklist']['channels'] or {*ctx.member.role_ids} & {*g_cfg['blacklist']['roles']}



@base_h.with_on_parser_error
async def on_parser_error(ctx: tj.abc.Context, error: tj.errors.ParserError) -> None:
    await err_reply(ctx, content=f"❌ You've given an invalid input: `{error}`")


@base_h.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    if isinstance(error, hk.ForbiddenError):
        await ctx.respond("⛔ Lacked enough permissions to execute the command.")
        return True

    # error_tb = f"\n```py\n{''.join(tb.format_exception(type(error), value=error, tb=error.__traceback__))}```"
    error_tb = '`%s`' % error

    await ctx.respond(f"⁉️ An unhandled error occurred: {error_tb}")
    return False


@base_h.with_pre_execution
async def pre_execution(ctx: tj.abc.Context, cfg: al.Injected[GuildConfig]) -> None:
    cfg.setdefault(str(ctx.guild_id), {})


def infer_guild(g_inf: GuildOrRESTInferable, /) -> hk.Snowflakeish:
    if isinstance(g_inf, hk.Snowflakeish):
        return g_inf
    assert g_inf.guild_id
    return g_inf.guild_id


def get_pref(ctx: Contextish, /):
    if isinstance(ctx, tj.abc.MessageContext):
        return next(iter(ctx.client.prefixes))
    if isinstance(ctx, tj.abc.SlashContext):
        return '/'
    if isinstance(ctx, tj.abc.AppCommandContext):
        return '.>'
    return '/'


async def fetch_permissions(ctx: Contextish, /) -> hk.Permissions:
    if isinstance(ctx, tj.abc.Context):
        member = ctx.member
        assert member
        auth_perms = await tj.utilities.fetch_permissions(
            ctx.client, member, channel=ctx.channel_id
        )
    else:
        member = ctx.member
        assert member
        auth_perms = member.permissions
    return auth_perms


def get_client(any_: t.Optional[t.Any] = None, /):
    if isinstance(any_, tj.abc.Context):
        return any_.client
    else:
        from src.client import client

        return client


def get_rest(g_r_inf: RESTInferable, /):
    if isinstance(g_r_inf, tj.abc.Context):
        return g_r_inf.rest
    return g_r_inf.app.rest


def get_cmd_n(ctx: tj.abc.Context, /):
    cmd = ctx.command
    if isinstance(cmd, tj.abc.MessageCommand):
        return next(iter(cmd.names))
    assert isinstance(cmd, tj.abc.SlashCommand | tj.abc.MenuCommand)
    return cmd.name
