from .errors import *

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

_T_co = t.TypeVar('_T_co', covariant=True)
Required = t.Union[_T_co, None]
VoidCoroutine = t.Coroutine[t.Any, t.Any, None]
EditableComponentsType = (
    hk.api.ButtonBuilder[hk.api.ActionRowBuilder]
    | hk.api.SelectMenuBuilder[hk.api.ActionRowBuilder]
)


TIME_REGEX = re.compile(
    r"^((\d+):)?([0-5][0-9]|[0-9]):([0-5][0-9]|[0-9])(.([0-9]{1,3}))?$"
)
TIME_REGEX_2 = re.compile(
    r"^(?!\s*$)((\d+)h)?(([0-9]|[0-5][0-9])m)?(([0-9]|[0-5][0-9])s)?(([0-9]|[0-9][0-9]|[0-9][0-9][0-9])ms)?$"
)
YOUTUBE_REGEX = re.compile(
    r"^(?:https?:)?(?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed)(?:\.php)?(?:\?.*v=|\/))([a-zA-Z0-9\_-]{7,15})(?:[\?&][a-zA-Z0-9\_-]+=[a-zA-Z0-9\_-]+)*(?:[&\/\#].*)?$"
)
URL_REGEX = re.compile(
    r'^(?:http|ftp)s?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$',
    re.I,
)
GENIUS_REGEX = re.compile(r'\d*Embed')
GENIUS_REGEX_2 = re.compile(r'^.+ Lyrics\n')
# LYRICS_URL = 'https://some-random-api.ml/lyrics?title='

TIMEOUT = 60
RETRIES = 3
Q_DIV = 15

hooks = tj.AnyHooks()
guild_c = tj.checks.GuildCheck(
    error_message="🙅 Commands can only be used in guild channels"
)
ytmusic = YTMusic()
genius = lg.Genius(os.environ['GENIUS_ACCESS_TOKEN'])
genius.verbose = False
loop = asyncio.get_event_loop()


GuildConfig = t.NewType('GuildConfig', dict[str, dict[str, t.Any]])


@a.define(hash=True, init=False, frozen=True)
class NullType(object):
    ...


_S_co = t.TypeVar('_S_co', covariant=True)
NULL = NullType()
NullOr = t.Union[_S_co, NullType]


class LyricsData(t.NamedTuple):
    source: str
    lyrics: str
    title: str
    artist: str
    thumbnail: str
    url: t.Optional[str] = None
    artist_icon: t.Optional[str] = None
    artist_url: t.Optional[str] = None


async def get_lyrics_yt(song: str, /) -> t.Optional[LyricsData]:
    queried = ytmusic.search(song, 'songs') + ytmusic.search(song, 'videos')  # type: ignore
    if not queried:
        return
    track_data_0 = queried[0]['videoId']  # type: ignore
    watches = ytmusic.get_watch_playlist(track_data_0)  # type: ignore
    track_data = watches['tracks'][0]  # type: ignore
    if watches['lyrics'] is None:
        return

    lyrics_id = watches['lyrics']  # type: ignore
    assert isinstance(lyrics_id, str)
    lyrics: dict[str, str] = ytmusic.get_lyrics(lyrics_id)  # type: ignore
    source: str = lyrics['source'].replace("Source: ", '')  # type: ignore

    return LyricsData(
        title=track_data['title'],  # type: ignore
        lyrics=lyrics['lyrics'],
        thumbnail=track_data['thumbnail'][-1]['url'],  # type: ignore
        artist=" & ".join((a['name'] for a in track_data['artists'])),  # type: ignore
        source=source,
    )


async def get_lyrics_ge_2(song: str, /) -> t.Optional[LyricsData]:
    for _ in range(RETRIES):
        try:
            song_0 = genius.search_song(song, get_full_info=False)  # type: ignore
            if not song_0:
                return

            lyrics = genius.lyrics(song_url=song_0.url, remove_section_headers=True)  # type: ignore

            if not lyrics:
                return

            lyrics = GENIUS_REGEX_2.sub('', GENIUS_REGEX.sub('', lyrics))

            artist = song_0.primary_artist
            return LyricsData(
                title=song_0.title,  # type: ignore
                url=song_0.url,  # type: ignore
                artist=song_0.artist,  # type: ignore
                lyrics=lyrics,
                thumbnail=song_0.song_art_image_url,  # type: ignore
                source="Genius",
                artist_icon=artist.image_url,  # type: ignore
                artist_url=artist.url,  # type: ignore
            )
        except rq.exceptions.Timeout:
            continue


async def get_lyrics(song: str, /) -> dict[str, LyricsData]:
    tests = (get_lyrics_ge_2(song), get_lyrics_yt(song))
    if not any(lyrics := await asyncio.gather(*tests)):
        raise LyricsNotFound
    return {l.source: l for l in lyrics if l}


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
    r_inf: GuildOrRESTInferable,
    /,
    *,
    del_after: float = 3.5,
    ensure_result: bool = False,
    channel: t.Optional[hk.GuildTextChannel] = None,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    return await reply(r_inf, hidden=True, ensure_result=ensure_result, channel=channel, delete_after=del_after, **kwargs)  # type: ignore


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
    ctx_: Contextish,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[False] = False,
    **kwargs: t.Any,
) -> t.Optional[hk.Message]:
    ...


@t.overload
async def reply(
    ctx_: Contextish,
    /,
    *,
    hidden: bool = False,
    ensure_result: t.Literal[True] = True,
    **kwargs: t.Any,
) -> hk.Message:
    ...


async def reply(
    g_r_inf: GuildOrRESTInferable,
    /,
    *,
    hidden: bool = False,
    ensure_result: bool = False,
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


def disable_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    predicates: t.Callable[[EditableComponentsType], bool] = lambda _: True,
) -> tuple[hk.api.ActionRowBuilder, ...]:
    return edit_components(
        rest,
        *action_rows,
        edits=lambda x: x.set_is_disabled(True),
        reverts=lambda x: x.set_is_disabled(False),
        predicates=predicates,
    )


_TC = t.TypeVar(
    '_TC',
    hk.api.ComponentBuilder,
    hk.api.ButtonBuilder[hk.api.ActionRowBuilder],
    hk.api.SelectMenuBuilder[hk.api.ActionRowBuilder],
)


def edit_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    edits: t.Callable[[_TC], _TC],
    reverts: t.Callable[[_TC], _TC] = lambda _: _,
    predicates: t.Callable[[_TC], bool] = lambda _: True,
) -> tuple[hk.api.ActionRowBuilder]:
    action_rows_ = list(action_rows)
    for a in action_rows_:
        components = a.components
        a = rest.build_action_row()
        for c in map(
            lambda c_: (edits(c_) if predicates(c_) else reverts(c_)),
            components,
        ):
            a.add_component(c)
    return tuple(action_rows_)


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
        finally:
            return

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


def with_message_menu_template(func: t.Callable[P_, VoidCoroutine], /):
    async def inner(*args: P_.args, **kwargs: P_.kwargs):
        ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)
        msg = next((a for a in args if isinstance(a, hk.Message)), None)
        assert ctx and msg

        if not msg.content:
            await err_reply(ctx, content="❌ Cannot process an empty message")
            return

        await func(*args, **kwargs)

    return inner


@hooks.with_on_parser_error
async def on_parser_error(ctx: tj.abc.Context, error: tj.errors.ParserError) -> None:
    await err_reply(ctx, content=f"❌ You've given an invalid input: `{error}`")


@hooks.with_on_error
async def on_error(ctx: tj.abc.Context, error: Exception) -> bool:
    if isinstance(error, hk.ForbiddenError):
        await ctx.respond("⛔ Lacked enough permissions to execute the command.")
        return True

    # error_tb = f"\n```py\n{''.join(tb.format_exception(type(error), value=error, tb=error.__traceback__))}```"
    error_tb = '`%s`' % error

    await ctx.respond(f"⁉️ An unhandled error occurred: {error_tb}")
    return False


@hooks.with_pre_execution
async def pre_execution(
    ctx: tj.abc.Context, cfg: GuildConfig = tj.inject(type=GuildConfig)
) -> None:
    cfg.setdefault(str(ctx.guild_id), {})


def curr_time_ms() -> int:
    return time.time_ns() // 1_000_000


def ms_stamp(ms: int, /) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return (
        (f'{h:02}:' if h else '')
        + f'{m:02}:{s:02}'
        + (f'.{ms:03}' if not (h or m or s) else '')
    )


def stamp_ms(str_: str, /) -> int:
    VALID_FORMAT = "00:00.204, 1:57, 2:00:09 | 400ms, 7m51s, 5h2s99ms"
    singl_z = ['0']
    if match := TIME_REGEX.fullmatch(str_):
        match_ = singl_z + list(match.groups('0'))
        match_ += singl_z * (7 - len(match.groups()))
        ms = int(match_[6])
        s = int(match_[4])
        m = int(match_[3])
        h = int(match_[2])
    elif match := TIME_REGEX_2.fullmatch(str_):
        match_ = singl_z + list(match.groups('0'))
        match_ += singl_z * (9 - len(match.groups()))
        ms = int(match_[8])
        s = int(match_[6])
        m = int(match_[4])
        h = int(match_[2])
    else:
        raise InvalidArgument(Argument(str_, VALID_FORMAT))
    return (((h * 60 + m) * 60 + s)) * 1000 + ms


def wr(
    str_: str,
    limit: int = 60,
    replace_with: str = '…',
    /,
    *,
    block_friendly: bool = True,
) -> str:
    str_ = str_.replace("'", '′').replace('"', '″') if block_friendly else str_
    return (
        str_ if len(str_) <= limit else str_[: limit - len(replace_with)] + replace_with
    )


def format_flags(flags: e.Flag, /) -> str:
    return ' & '.join(f.replace('_', ' ').title() for f in str(flags).split('|'))


def infer_guild(g_inf: GuildOrRESTInferable, /) -> hk.Snowflakeish:
    if isinstance(g_inf, hk.Snowflakeish):
        return g_inf
    assert g_inf.guild_id
    return g_inf.guild_id


def get_pref(ctx: Contextish):
    if isinstance(ctx, tj.abc.MessageContext):
        return next(iter(ctx.client.prefixes))
    if isinstance(ctx, tj.abc.SlashContext):
        return '/'
    if isinstance(ctx, tj.abc.AppCommandContext):
        return '.>'
    return '/'


async def fetch_permissions(ctx: Contextish) -> hk.Permissions:
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


def get_client(any_: t.Optional[Contextish] = None):
    if isinstance(any_, tj.abc.Context):
        return any_.client
    else:
        from src.client import client

        return client


def get_rest(g_r_inf: RESTInferable):
    if isinstance(g_r_inf, tj.abc.Context):
        return g_r_inf.rest
    return g_r_inf.app.rest


def get_cmd_n(ctx: tj.abc.Context):
    cmd = ctx.command
    if isinstance(cmd, tj.abc.MessageCommand):
        return next(iter(cmd.names))
    assert isinstance(cmd, tj.abc.SlashCommand | tj.abc.MenuCommand)
    return cmd.name


_E = t.TypeVar('_E')


def chunk(seq: t.Sequence[_E], n: int, /) -> t.Generator[t.Sequence[_E], None, None]:
    """Yield successive `n`-sized chunks from `seq`."""
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def chunk_b(seq: t.Sequence[_E], n: int, /) -> t.Generator[t.Sequence[_E], None, None]:
    """Yield successive `n`-sized chunks from `seq`, backwards."""
    start = 0
    for end in range(len(seq) % n, len(seq) + 1, n):
        yield seq[start:end]
        start = end


def inj_glob(pattern: str):
    if os.environ.get('IN_DOCKER', False):
        p = pl.Path('.') / 'shared'
    else:
        p = pl.Path('.') / '..'
    return p.glob(pattern)
