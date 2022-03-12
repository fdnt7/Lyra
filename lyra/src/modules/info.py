import typing as t
import logging

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv


from src.lib.music import music_h, auto_connect_vc, generate_queue_embeds__
from src.lib.utils import (
    Q_DIV,
    EitherContext,
    EmojiRefs,
    EditableComponentsType,
    guild_c,
    reply,
    err_reply,
    trigger_thinking,
    disable_components,
)
from src.lib.errors import QueryEmpty, LyricsNotFound
from src.lib.extras import TIMEOUT, ms_stamp, wr, get_lyrics
from src.lib.checks import Checks, check
from src.lib.lavaimpl import get_queue, access_queue


info = tj.Component(name='Info', strict=True).add_check(guild_c).set_hooks(music_h)


logger = logging.getLogger('info       ')
logger.setLevel(logging.DEBUG)


# Ping


@tj.as_slash_command('ping', "Shows the bot's latency")
#
@tj.as_message_command('ping', 'latency', 'pi', 'lat', 'late', 'png')
async def ping(ctx: tj.abc.Context):
    """
    Shows the bot's latency
    """
    assert ctx.shards
    await reply(ctx, content=f"📶 **{int(ctx.shards.heartbeat_latency*1000)}** ms")


# Now Playing


@tj.as_slash_command('now-playing', "Displays info of the current track")
#
@tj.as_message_command(
    'nowplaying', 'now-playing', 'np', 'now', 'curr', 'current', 'crr'
)
async def nowplaying(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """
    Displays info on the currently playing song.
    """
    await nowplaying_(ctx, lvc=lvc)


@check(Checks.CONN | Checks.QUEUE | Checks.PLAYING)
async def nowplaying_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Displays info on the currently playing song."""
    assert not ((ctx.guild_id is None) or (ctx.cache is None) or (ctx.member is None))

    q = await get_queue(ctx, lvc)
    e = '⏹️' if q.is_stopped else ('▶️' if q.is_paused else '⏸️')

    curr_t = q.current
    assert curr_t
    assert q.np_position

    t_info = curr_t.track.info
    req = ctx.cache.get_member(ctx.guild_id, curr_t.requester)
    assert req is not None

    title_pad = int(len(t_info.title) // 1.143)
    username_pad = (27 * len(ctx.member.display_name) + 97) // 31
    padding = min(54, max(title_pad, username_pad)) - 2

    song_len = ms_stamp(t_info.length)
    np_pos = ms_stamp(q.np_position)

    progress = round(
        (q.np_position / t_info.length)
        * (padding + 12 - len(''.join((np_pos, song_len))))
    )

    desc = (
        f'📀 **{t_info.author}**',
        f"{e} `{np_pos:─<{padding}}{song_len:─>12}`".replace('─', ' ', 1)[::-1]
        .replace('─', ' ', 1)[::-1]
        .replace('─', '▬', progress),
    )

    color = None if q.is_paused else q.curr_t_palette[1]

    embed = (
        hk.Embed(
            title=f"{'🎶 ' if not q.is_paused else ''}{t_info.title}",
            description="%s\n\n%s" % desc,
            url=t_info.uri,
            color=color,
            # timestamp=dt.datetime.now().astimezone(),
        )
        .set_author(name="Now playing")
        .set_footer(
            f"Requested by: {req.display_name}",
            icon=req.avatar_url or ctx.author.default_avatar_url,
        )
        .set_thumbnail(q.curr_t_thumbnail)
    )
    await reply(ctx, hidden=True, embed=embed)


# Search


@tj.with_greedy_argument('query')
@tj.with_parser
@tj.as_message_command('search', 'se', 'f', 'yt', 'youtube')
#
@tj.with_str_slash_option('query', "What to be queried?")
@tj.as_slash_command(
    'search',
    "Searches for tracks on youtube from your query and lets you hear a part of it",
)
async def search(
    ctx: EitherContext,
    query: str,
    lvc: al.Injected[lv.Lavalink],
):
    await search_(ctx, query, lvc=lvc)


@info.with_menu_command
@tj.as_message_menu('Search this song up')
async def search_c(
    ctx: tj.abc.MenuContext,
    msg: hk.Message,
    lvc: al.Injected[lv.Lavalink],
) -> None:
    if not msg.content:
        await err_reply(ctx, content="❌ Cannot process an empty message")
        return
    await search_(ctx, msg.content, lvc=lvc)


@auto_connect_vc
@check(Checks.CONN | Checks.SPEAK)
async def search_(ctx: EitherContext, query: str, /, *, lvc: lv.Lavalink) -> None:
    from .queue import play__, enqueue_track__
    from .playback import stop__, continue__

    erf = ctx.client.get_type_dependency(EmojiRefs)
    assert ctx.guild_id and erf

    query = query.strip("<>|")

    QUERIED_N = 10
    PREVIEW_START = 50_000
    PREVIEW_TIME = 30_000

    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert bot

    async with trigger_thinking(ctx):
        _queried = await lvc.auto_search_tracks(query)
    if _queried.load_type in ('TRACK_LOADED', 'PLAYLIST_LOADED'):
        await play__(ctx, lvc, tracks=_queried, respond=True)
        await reply(
            ctx,
            hidden=True,
            content="💡 It is best to input a search query to the `/search` command. *For links, use `/play` instead*",
        )
        return

    queried = _queried.tracks
    if not queried:
        raise QueryEmpty

    queried_msg = "```css\n%s\n```" % (
        "\n".join(
            f"{i: >2}. {ms_stamp(t.info.length):>9} | {wr(t.info.title, 48)}"
            for i, t in enumerate(queried[:QUERIED_N], 1)
        )
    )

    pre_row_1 = ctx.rest.build_action_row()
    components: list[hk.api.ActionRowBuilder] = []

    for i in (pre_row_1_ := map(str, range(1, 1 + len(queried[:5])))):
        pre_row_1.add_button(hk.ButtonStyle.SECONDARY, i).set_label(
            i
        ).add_to_container()
    if pre_row_1_:
        components.append(pre_row_1)

        pre_row_2 = ctx.rest.build_action_row()
        for j in (pre_row_2_ := map(str, range(6, 6 + len(queried[5:10])))):
            pre_row_2.add_button(hk.ButtonStyle.SECONDARY, j).set_label(
                j
            ).add_to_container()
        if pre_row_2_:
            components.append(pre_row_2)

    ops_row = ctx.rest.build_action_row()
    ops_row.add_button(hk.ButtonStyle.SUCCESS, 'enqueue').set_label(
        "＋ Enqueue"
    ).add_to_container()

    ops_row.add_button(hk.ButtonStyle.PRIMARY, 'link').set_label(
        "Get Link"
    ).add_to_container()
    ops_row.add_button(hk.ButtonStyle.DANGER, 'cancel').set_emoji(
        erf['exit_b']
    ).add_to_container()
    components.append(ops_row)

    embed = hk.Embed(
        title=f"🔎 Searching for `{query}`",
    ).add_field("Search results", value=queried_msg)
    msg = await reply(
        ctx,
        ensure_result=True,
        embed=embed,
        components=components,
    )
    ch = await ctx.fetch_channel()

    async def on_going_tracks() -> bool:
        return bool((q := await get_queue(ctx, lvc)) and q.current)

    prior_stop = (await get_queue(ctx, lvc)).is_stopped

    with bot.stream(hk.InteractionCreateEvent, timeout=TIMEOUT).filter(
        lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.user == ctx.author
        and e.interaction.message == msg
    ) as stream:
        selected: t.Optional[str] = None
        sel_msg: t.Optional[hk.Message] = None

        if not await on_going_tracks():
            await stop__(ctx, lvc)

        async for event in stream:
            inter = event.interaction
            assert isinstance(inter, hk.ComponentInteraction)
            key = inter.custom_id

            if key == 'cancel':
                if not await on_going_tracks():
                    await lvc.stop(
                        ctx.guild_id,
                    )
                if sel_msg:
                    await ch.delete_messages(sel_msg)
                await ctx.delete_initial_response()
                if not prior_stop:
                    await continue__(ctx, lvc)
                return

            if key in map(str, range(1, QUERIED_N + 1)):
                track = queried[int(key) - 1]
                if sel_msg:
                    await ch.delete_messages(sel_msg)

                selected = key

                await inter.create_initial_response(
                    hk.ResponseType.DEFERRED_MESSAGE_CREATE,
                )
                if await on_going_tracks():
                    sel_msg = await reply(
                        inter,
                        ensure_result=True,
                        content=f"👆 Selected track **`{key}`** `({track.info.title})`",
                    )
                    continue

                await lvc.play(ctx.guild_id, track).start_time_millis(
                    PREVIEW_START
                ).finish_time_millis(PREVIEW_START + PREVIEW_TIME).replace(True).start()

                sel_msg = await reply(
                    inter,
                    ensure_result=True,
                    content=f"🎧 Playing a preview of **`{key}`** `({track.info.title})`",
                    delete_after=PREVIEW_TIME / 1000,
                )
                continue

            if selected is None:
                await err_reply(inter, content=f"❗ No tracks has been selected yet")
                continue
            selected_t = queried[int(selected) - 1]
            if key == 'enqueue':
                await inter.create_initial_response(
                    hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
                )
                if not await on_going_tracks():
                    await lvc.stop(
                        ctx.guild_id,
                    )
                if sel_msg:
                    await ch.delete_messages(sel_msg)
                if not prior_stop:
                    await continue__(ctx, lvc)
                async with access_queue(ctx, lvc) as q:
                    await enqueue_track__(
                        ctx,
                        lvc,
                        track=selected_t,
                        queue=q,
                        respond=False,
                        ignore_stop=True,
                    )
                await inter.edit_initial_response(
                    f"**🔎`＋`** Added `{selected_t.info.title}` to the queue",
                    embed=None,
                    user_mentions=False,
                    components=[],
                )
                return
            elif key == 'link':
                await reply(
                    inter, hidden=True, content=f"🌐 Link is {selected_t.info.uri}"
                )
            else:
                raise NotImplementedError

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, *components),)
        )
        if not prior_stop:
            await continue__(ctx, lvc)


# Queue


@tj.as_slash_command('queue', "Lists out the entire queue")
#
@tj.as_message_command('queue', 'q', 'all')
async def queue(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    await queue_(ctx, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN)
async def queue_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink):
    q = await get_queue(ctx, lvc)
    pages = await generate_queue_embeds__(ctx, lvc)
    pages_n = len(pages)

    erf = ctx.client.get_type_dependency(EmojiRefs)
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert bot and erf

    def _page_row(*, cancel_b: bool = False):
        row = ctx.rest.build_action_row()

        row.add_button(hk.ButtonStyle.SECONDARY, 'start').set_emoji(
            '⏪'
        ).add_to_container()

        row.add_button(hk.ButtonStyle.SECONDARY, 'prev').set_emoji(
            '◀️'
        ).add_to_container()

        if cancel_b:
            _3rd_b = row.add_button(hk.ButtonStyle.DANGER, 'delete').set_emoji(
                erf['exit_b']
            )
        else:
            _3rd_b = row.add_button(hk.ButtonStyle.PRIMARY, 'main').set_emoji('⏺️')
        _3rd_b.add_to_container()

        row.add_button(hk.ButtonStyle.SECONDARY, 'next').set_emoji(
            '▶️'
        ).add_to_container()

        row.add_button(hk.ButtonStyle.SECONDARY, 'end').set_emoji(
            '⏩'
        ).add_to_container()

        return row

    _i_ori = (q.pos - 2) // Q_DIV + 1
    i = _i_ori

    def _update_buttons(b: EditableComponentsType):
        assert isinstance(b, hk.api.ButtonBuilder)
        return (
            (not pages[:i] and b.emoji == '◀️')
            or (not pages[i + 1 :] and b.emoji == '▶️')
            or (i == 0 and b.emoji == '⏪')
            or (i == pages_n - 1 and b.emoji == '⏩')
        )

    embed = pages[i].set_author(name=f"Page {i+1}/{pages_n}")
    msg = await reply(
        ctx,
        ensure_result=True,
        embed=embed,
        components=(
            *disable_components(
                ctx.rest, (row := _page_row(cancel_b=True)), predicates=_update_buttons
            ),
        ),
    )

    with bot.stream(hk.InteractionCreateEvent, timeout=TIMEOUT).filter(
        lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.message == msg
        and e.interaction.user.id == ctx.author.id
    ) as stream:
        _row = row
        async for event in stream:
            inter = event.interaction
            assert isinstance(inter, hk.ComponentInteraction)
            await inter.create_initial_response(
                hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
            )

            key = inter.custom_id

            if key == 'main':
                i = _i_ori
            elif key == 'next':
                i += 1
            elif key == 'prev':
                i -= 1
            elif key == 'start':
                i = 0
            elif key == 'end':
                i = pages_n - 1
            elif key == 'delete':
                await inter.delete_initial_response()
                return

            _row = _page_row(cancel_b=i == _i_ori)
            embed = pages[i].set_author(name=f"Page {i+1}/{pages_n}")

            await inter.edit_initial_response(
                embed=embed,
                components=(
                    *disable_components(
                        inter.app.rest, _row, predicates=_update_buttons
                    ),
                ),
            )

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, _row),)
        )


# Lyrics


@tj.with_str_slash_option(
    'song', "What song? (If not given, the current song)", default=None
)
@tj.as_slash_command('lyrics', 'Attempts to find the lyrics of the current song')
#
@tj.with_greedy_argument('song', default=None)
@tj.with_parser
@tj.as_message_command('lyrics', 'ly')
async def lyrics(
    ctx: EitherContext,
    song: t.Optional[str],
    lvc: al.Injected[lv.Lavalink],
):
    """
    Attempts to find the lyrics of the current song
    """
    await lyrics_(ctx, song, lvc=lvc)


@check(Checks.CATCH_ALL)
async def lyrics_(
    ctx: EitherContext,
    song: t.Optional[str],
    /,
    *,
    lvc: lv.Lavalink,
) -> None:
    """Attempts to find the lyrics of the current song"""
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    erf = ctx.client.get_type_dependency(EmojiRefs)
    assert bot and erf

    if song is None:
        if not ((q := await get_queue(ctx, lvc)) and (np := q.current)):
            await err_reply(
                ctx, content=f"❌ Please specify a song title or play a track first"
            )
            return
        else:
            song = np.track.info.title

    # import cProfile
    # import pstats

    # async def f():
    sel_row = ctx.rest.build_action_row()
    act_row = ctx.rest.build_action_row()

    ly_sel = sel_row.add_select_menu('ly_sel')
    cancel_b = act_row.add_button(hk.ButtonStyle.DANGER, 'delete').set_emoji(
        erf['exit_b']
    )

    try:
        async with trigger_thinking(ctx):
            lyrics = await get_lyrics(song)
    except LyricsNotFound:
        await err_reply(ctx, content=f"❓ Could not find any lyrics for the song")
        return

    for source in lyrics:
        (
            ly_sel.add_option(source, source)
            .set_emoji(erf[source.casefold()])
            .set_description(f"The lyrics fetched from {source}")
            .add_to_menu()
        )

    icons: tuple[str] = tuple(erf[source.casefold()].url for source in lyrics)

    # (
    #     ly_sel.add_option('Cancel', 'cancel')
    #     .set_emoji('❌')
    #     .set_description("Delete this message")
    #     .add_to_menu()
    # )

    embeds = {
        ly.source: hk.Embed(
            title='🎤 ' + ly.title,
            description=ly.lyrics
            if len(ly.lyrics) <= 4_096
            else (
                wr(
                    ly.lyrics,
                    4_096,
                    '...'
                    if not ly.url
                    else f"{wr(ly.lyrics, 3_996, '...')}\n\n🔺 **View full lyrics on the link in the title**",
                )
            ),
            url=ly.url,
        )
        .set_thumbnail(ly.thumbnail)
        .set_author(name=ly.artist, icon=ly.artist_icon, url=ly.artist_url)
        .set_footer(ly.source, icon=i)
        for ly, i in zip(lyrics.values(), icons)
    }

    ly_sel.set_placeholder("Select a Lyric source")

    ly_sel.add_to_container()
    cancel_b.add_to_container()
    msg = await reply(
        ctx,
        ensure_result=True,
        embed=next(iter(embeds.values())),
        components=[sel_row, act_row],
    )

    with bot.stream(hk.InteractionCreateEvent, timeout=TIMEOUT).filter(
        lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.message == msg
        and e.interaction.user.id == ctx.author.id
    ) as stream:
        _last_sel: t.Optional[str] = None
        async for event in stream:
            inter = event.interaction
            assert isinstance(inter, hk.ComponentInteraction)
            await inter.create_initial_response(
                hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
            )

            sel = next(iter(inter.values), None)
            key = inter.custom_id

            if key == 'delete':
                await inter.delete_initial_response()
                return

            assert sel is not None
            if sel == _last_sel:
                continue
            _last_sel = sel
            await inter.edit_initial_response(embed=embeds[sel])

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, sel_row),)
        )

    # with cProfile.Profile() as pr:
    #     await f()

    # stats = pstats.Stats(pr)
    # stats.sort_stats(pstats.SortKey.TIME)
    # stats.print_stats()
    # stats.dump_stats(filename='needs_profiling.prof')


# -


loader = info.load_from_scope().make_loader()
