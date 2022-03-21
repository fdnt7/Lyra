import typing as t
import asyncio
import functools as ft
import contextlib as ctxlib

import hikari as hk
import tanjun as tj
import alluka as al

from hikari.permissions import Permissions as hkperms
from hikari.messages import MessageFlag as msgflag

from .extras import NULL, TIMEOUT, VoidCoroutine, join_and


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
MentionableType = hk.GuildChannel | hk.Role | hk.Member

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
async def err_say(
    event: GuildInferableEvents | hk.Snowflakeish,
    /,
    *,
    del_after: float = 3.5,
    channel: hk.GuildTextChannel = ...,
    **kwargs: t.Any,
) -> hk.Message:
    ...


@t.overload
async def err_say(
    ctx_: Contextish,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: t.Literal[False] = False,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    ...


@t.overload
async def err_say(
    ctx_: Contextish,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: t.Literal[True] = True,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def err_say(
    g_r_inf: GuildOrRESTInferable,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: bool = False,
    channel: t.Optional[hk.GuildTextChannel] = None,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    return await say(g_r_inf, hidden=True, ensure_result=ensure_result, channel=channel, delete_after=del_after, **kwargs)  # type: ignore


@t.overload
async def ephim_say(
    g_: GuildInferableEvents | hk.Snowflakeish,
    /,
    *,
    channel: hk.GuildTextChannel = ...,
    **kwargs: t.Any,
) -> hk.Message:
    ...


@t.overload
async def ephim_say(
    ctx_: Contextish,
    /,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def ephim_say(
    g_r_inf: GuildOrRESTInferable,
    /,
    *,
    channel: t.Optional[hk.GuildTextChannel] = None,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    if isinstance(g_r_inf, hk.ComponentInteraction | tj.abc.AppCommandContext):
        return await say(g_r_inf, hidden=True, channel=channel, **kwargs)


@t.overload
async def say(
    g_: GuildInferableEvents | hk.Snowflakeish,
    /,
    *,
    hidden: bool = False,
    channel: hk.GuildTextChannel = ...,
    **kwargs: t.Any,
) -> hk.Message:
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
) -> t.Optional[hk.Message]:
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
) -> t.Optional[hk.Message]:
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
    g_r_inf: GuildOrRESTInferable,
    /,
    *,
    hidden: bool = False,
    follow_up: bool = False,
    ensure_result: bool = False,
    show_author: bool = False,
    channel: t.Optional[hk.GuildTextChannel] = None,
    **kwargs: t.Any,
):
    msg: t.Optional[hk.Message] = None
    if kwargs.get('embed', hk.UNDEFINED) is hk.UNDEFINED:
        kwargs['embed'] = None
    if kwargs.get('components', hk.UNDEFINED) is hk.UNDEFINED:
        kwargs['components'] = ()

    try:
        if isinstance(g_r_inf, hk.ComponentInteraction | GuildInferableEvents):
            kwargs.pop('delete_after', None)

        flags = msgflag.EPHEMERAL if hidden else hk.UNDEFINED
        if isinstance(g_r_inf, GuildInferableEvents):
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


_C_contra = t.TypeVar(
    '_C_contra',
    bound=hk.api.ComponentBuilder,
    contravariant=True,
)


def edit_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    edits: t.Callable[[_C_contra], _C_contra],
    reverts: t.Callable[[_C_contra], _C_contra] = lambda _: _,
    predicates: t.Callable[[_C_contra], bool] = lambda _: True,
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


def extract_content(msg: hk.Message):
    return msg.content


async def init_confirmation_prompt(ctx: tj.abc.Context):
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert bot

    cmd_n = ''.join((get_pref(ctx), '~ ', get_cmd_n(ctx)))
    callback = getattr(ctx.command, 'callback', None)
    if callback:
        docs = callback.__doc__
    else:
        docs = None

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
        title=f'⚠️ Confirmation prompt for command `{cmd_n}`',
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

    inter = event.interaction
    assert isinstance(inter, hk.ComponentInteraction)
    await inter.create_initial_response(hk.ResponseType.DEFERRED_MESSAGE_UPDATE)
    return inter.custom_id == 'prompt_y'


_P_e = t.ParamSpec('_P_e')


def suppress_embeds(func: t.Callable[_P_e, VoidCoroutine]):
    @ft.wraps(func)
    async def inner(*args: _P_e.args, **kwargs: _P_e.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.MessageContext)), NULL)
        assert ctx
        assert ctx.guild_id and ctx.cache

        bot_u = ctx.cache.get_me()
        assert bot_u

        bot_m = ctx.cache.get_member(ctx.guild_id, bot_u)
        assert bot_m

        bot_perms = await tj.utilities.fetch_permissions(
            ctx.client, bot_m, channel=ctx.channel_id
        )
        if bot_perms & hkperms.MANAGE_MESSAGES:
            await ctx.message.edit(flags=msgflag.SUPPRESS_EMBEDS)

        inj_func = tj.as_self_injecting(ctx.client)(func)
        await inj_func(*args, **kwargs)

    return inner


_P_mgT = t.ParamSpec('_P_mgT')


def with_message_command_group_template(func: t.Callable[_P_mgT, VoidCoroutine], /):
    @ft.wraps(func)
    async def inner(*args: _P_mgT.args, **kwargs: _P_mgT.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)
        assert ctx

        cmd = ctx.command
        assert isinstance(cmd, tj.abc.MessageCommandGroup)
        p = next(iter(ctx.client.prefixes))
        cmd_n = next(iter(cmd.names))
        sub_cmds_n = map(lambda s: next(iter(s.names)), cmd.commands)
        valid_cmds = ', '.join(
            f"`{p}~ {cmd_n} {sub_cmd_n} ...`" for sub_cmd_n in sub_cmds_n
        )
        await err_say(
            ctx,
            content=f"❌ This is a command group. Use the following instead:\n{valid_cmds}",
        )

        await func(*args, **kwargs)

    return inner


async def restricts_c(ctx: tj.abc.Context, /, *, cfg: al.Injected[GuildConfig]) -> bool:
    from src.modules.config import RESTRICTOR

    assert ctx.guild_id and ctx.member

    g_cfg = cfg[str(ctx.guild_id)]

    res_ch: dict[str, t.Any] = g_cfg.get('restricted_ch', {})
    res_r: dict[str, t.Any] = g_cfg.get('restricted_r', {})
    res_u: dict[str, t.Any] = g_cfg.get('restricted_u', {})

    ch_wl = res_ch.get('wl_mode', 0)
    r_wl = res_r.get('wl_mode', 0)
    u_wl = res_u.get('wl_mode', 0)

    res_ch_all: list[int] = res_ch.setdefault('all', [])
    res_r_all: list[int] = res_r.setdefault('all', [])
    res_u_all: list[int] = res_u.setdefault('all', [])

    author_perms = await tj.utilities.fetch_permissions(
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
        if not (cond := bool({*ctx.member.role_ids} & {*res_r_all})):
            await ephim_say(ctx, content="🚷 You aren't role whitelisted to use the bot")
        return cond

    if r_wl == -1 and {*ctx.member.role_ids} & {*res_r_all}:
        await ephim_say(ctx, content="🚷 You are role blacklisted from using the bot")
        return False

    if ch_wl == 1:
        if not (cond := ctx.channel_id in res_ch_all):
            await ephim_say(
                ctx,
                content=f"🚷 This channel isn't whitelisted to use the bot. Consider using the bot in {join_and(('<#%i>' % ch for ch in res_ch_all), and_='or')}",
            )
        return False

    if ch_wl == -1 and ctx.channel_id in res_ch_all:
        await ephim_say(
            ctx,
            content=f"🚷 This channel is blacklisted from using the bot. Refrain from using the bot in {join_and(('<#%i>' % ch for ch in res_ch_all), and_='or')}",
        )
        return False

    return True


@base_h.with_on_parser_error
async def on_parser_error(ctx: tj.abc.Context, error: tj.errors.ParserError) -> None:
    msg = f"❌ You've given an invalid input: `{error}` "
    if related_errs := getattr(error, 'errors', None):
        err_msg = '\n'.join(
            f'Cause-{i}: {next(iter(e.args))}' for i, e in enumerate(related_errs, 1)
        )
        msg += f"```arm\n{err_msg}```"
    await err_say(
        ctx,
        content=msg,
        del_after=3.5 if not related_errs else 6.5,
    )


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
        return '/'
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

    def _recurse(
        _cmd: tj.abc.ExecutableCommand[tj.abc.Context], _names: list[str]
    ) -> list[str]:
        if isinstance(_cmd, tj.abc.MessageCommand):
            _names.append(next(iter(_cmd.names)))
        elif isinstance(_cmd, tj.abc.SlashCommand | tj.abc.MenuCommand):
            _names.append(_cmd.name)

        if not (parent_cmd := getattr(_cmd, 'parent', None)):  # type: ignore
            return _names
        return _recurse(parent_cmd, _names)

    assert cmd
    return ''.join(_recurse(cmd, []))
