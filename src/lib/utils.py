import src.lib.consts as c

from .errors import *


Contextish = tj.abc.Context | hk.Snowflakeish
VoidCoroutine = t.Coroutine[t.Any, t.Any, None]
DisableableComponentsType = (
    hk.api.ButtonBuilder[hk.api.ActionRowBuilder]
    | hk.api.SelectMenuBuilder[hk.api.ActionRowBuilder]
)
DisableableComponents = hk.api.ButtonBuilder | hk.api.SelectMenuBuilder

Sentinel = object


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
FIELD_SLICE = 15

hooks = tj.AnyHooks()
guild_c = tj.checks.GuildCheck(
    error_message="🙅 Commands can only be used in guild channels"
)
ytmusic = YTMusic()
genius = lg.Genius(os.environ['GENIUS_ACCESS_TOKEN'])
genius.verbose = False
loop = asyncio.get_event_loop()


REMOVED: Sentinel = object()


@a.define(hash=True)
class GuildSettings(dict):
    pass


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
    queried = ytmusic.search(song, 'songs') + ytmusic.search(song, 'videos')
    if not queried:
        return
    track_data_0 = queried[0]['videoId']
    watches = ytmusic.get_watch_playlist(track_data_0)
    track_data = watches['tracks'][0]
    if watches['lyrics'] is None:
        return

    lyrics_id = watches['lyrics']
    assert isinstance(lyrics_id, str)
    lyrics = ytmusic.get_lyrics(lyrics_id)
    source = lyrics['source'].replace("Source: ", '')

    return LyricsData(
        title=track_data['title'],
        lyrics=lyrics['lyrics'],
        thumbnail=track_data['thumbnail'][-1]['url'],
        artist=" & ".join((a['name'] for a in track_data['artists'])),
        source=source,
    )


# async def get_lyrics_ge_1(song: str) -> t.Optional[LyricsData]:
#     async with aiohttp.request('GET', LYRICS_URL + song, headers={}) as r:
#         if not 200 <= r.status <= 299:
#             return
#         data = await r.json()
#         lyrics: str = data['lyrics']

#         if len(data['lyrics']) > 2_000:
#             links: str = data['links']['genius']
#             lyrics = f"{wr(lyrics, 1_900, '...')}\n\n**View full lyrics on:**\n{links}"

#         return LyricsData(
#             title=data['title'],
#             icon=c.GENIUS_ICON,
#             lyrics=lyrics,
#             thumbnail=data['thumbnail']['genius'],
#             author=data['author'],
#             source='Genius',
#         )


async def get_lyrics_ge_2(song: str, /) -> t.Optional[LyricsData]:
    for _ in range(RETRIES):
        try:
            song_0 = genius.search_song(song)
            if not song_0:
                return

            lyrics = genius.lyrics(song_url=song_0.url, remove_section_headers=True)

            if not lyrics:
                return

            lyrics = GENIUS_REGEX_2.sub('', GENIUS_REGEX.sub('', lyrics))

            artist = song_0.primary_artist
            return LyricsData(
                title=song_0.title,
                url=song_0.url,
                artist=song_0.artist,
                lyrics=lyrics,
                thumbnail=song_0.song_art_image_url,
                source="Genius",
                artist_icon=artist.image_url,
                artist_url=artist.url,
            )
        except rq.exceptions.Timeout:
            continue


async def get_lyrics(song: str, /) -> dict[str, LyricsData]:
    tests = (get_lyrics_ge_2, get_lyrics_yt)
    if not (lyrics := {l.source: l for t in tests if (l := await t(song))}):
        raise LyricsNotFound
    return lyrics


async def err_reply(ctx: tj.abc.Context, /, *, del_after: float = 3.5, **kwargs: t.Any):
    return await reply(ctx, hidden=True, delete_after=del_after, **kwargs)


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


async def reply(
    ctx: tj.abc.Context,
    /,
    *,
    hidden: bool = False,
    ensure_result: bool = False,
    **kwargs: t.Any,
):
    if isinstance(ctx, tj.abc.MessageContext):
        msg = await ctx.respond(**kwargs, reply=True)
    else:
        assert isinstance(ctx, tj.abc.SlashContext)
        flags = msgflag.EPHEMERAL if hidden else hk.UNDEFINED
        try:
            if ctx.has_responded:
                msg = await ctx.create_followup(**kwargs, flags=flags)
            else:
                msg = await ctx.create_initial_response(**kwargs, flags=flags)
        except (RuntimeError, hk.NotFoundError):
            msg = await ctx.edit_initial_response(**kwargs)

    return msg if not ensure_result else await ctx.fetch_last_response()


def disable_components(
    rest: hk.api.RESTClient,
    /,
    *action_rows: hk.api.ActionRowBuilder,
    predicates: t.Callable[[DisableableComponentsType], bool] = lambda _: True,
) -> tuple[hk.api.ActionRowBuilder, ...]:
    action_rows_ = list(action_rows)
    for a in action_rows_:
        components = a.components
        a = rest.build_action_row()
        for c in map(
            lambda c_: c_
            if not isinstance(c_, DisableableComponents)
            else (
                c_.set_is_disabled(True)
                if predicates(c_)
                else c_.set_is_disabled(False)
            ),
            components,
        ):
            assert isinstance(c, DisableableComponents)
            a.add_component(c)
    return tuple(action_rows_)


def trigger_thinking(flags: msgflag = msgflag.NONE, /):
    P = t.ParamSpec('P')

    def callback(func: t.Callable[P, VoidCoroutine]) -> t.Callable[P, VoidCoroutine]:
        async def inner(*args: P.args, **kwargs: P.kwargs):
            ctx = next((a for a in args if isinstance(a, tj.abc.Context)), None)

            assert ctx
            assert ctx.guild_id is not None
            if isinstance(ctx, tj.abc.MessageContext):
                ch = ctx.get_channel()
                assert ch is not None
                async with ch.trigger_typing():
                    await func(*args, **kwargs)
                return

            assert isinstance(ctx, tj.abc.SlashContext)
            try:
                if not ctx.has_responded:
                    await ctx.defer(flags)
            except RuntimeError:
                pass
            await func(*args, **kwargs)

        return inner

    return callback


P = t.ParamSpec('P')

def with_message_command_group_template(func: t.Callable[P, VoidCoroutine], /):
    async def inner(*args: P.args, **kwargs: P.kwargs):
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


def snowflakeify(ctx_g: Contextish, /):
    if isinstance(ctx_g, tj.abc.Context):
        assert ctx_g.guild_id is not None
        ctx_g = ctx_g.guild_id
    return ctx_g


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
