import typing as t

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv
import tanjun.annotations as ja

from ..lib.cmd import get_full_cmd_repr_from_identifier
from ..lib.cmd.ids import CommandIdentifier as C
from ..lib.cmd.compose import with_identifier
from ..lib.utils import (
    Q_CHUNK,
    TIMEOUT,
    EitherContext,
    EmojiRefs,
    limit_img_size_by_guild,
    say,
    err_say,
    extract_content,
    trigger_thinking,
    disable_components,
    with_annotated_args,
)
from ..lib.music import stop, unstop
from ..lib.musicutils import generate_queue_embeds, __init_component__
from ..lib.errors import QueryEmpty, LyricsNotFound
from ..lib.extras import Option, Result, to_stamp, wr, get_lyrics
from ..lib.lava.utils import get_queue, access_queue
from ..lib.cmd.compose import Binds, Checks, with_cmd_checks, with_cmd_composer


info = __init_component__(__name__)


# ~


# /now-playing


with_np_cmd_check = with_cmd_checks(Checks.CONN | Checks.QUEUE | Checks.PLAYING)


@with_np_cmd_check(C.NOWPLAYING)
# -
@tj.as_slash_command('now-playing', "Displays info of the current track")
@tj.as_message_command(
    'now-playing', 'nowplaying', 'np', 'now', 'curr', 'current', 'crr'
)
async def nowplaying_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
) -> None:
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

    song_len = to_stamp(t_info.length)
    np_pos = to_stamp(q.np_position)

    progress = round(
        (q.np_position / t_info.length)
        * (padding + 12 - len(''.join((np_pos, song_len))))
    )

    desc = (
        f'👤 **{t_info.author}**',
        f"{e} `{np_pos:─<{padding}}{song_len:─>12}`".replace('─', ' ', 1)[::-1]
        .replace('─', ' ', 1)[::-1]
        .replace('─', '▬', progress),
    )

    color = q.curr_t_palette[1] if q.is_playing else None

    if thumb := q.curr_t_thumbnail:
        thumb = limit_img_size_by_guild(thumb, ctx, ctx.cache)
    embed = (
        hk.Embed(
            title=f"{'🎶 ' if q.is_playing else ''}__**`#{q.pos + 1}`**__  {t_info.title}",
            description="%s\n\n%s" % desc,
            url=t_info.uri,
            color=color,
            # timestamp=dt.datetime.now().astimezone(),
        )
        .set_author(name="Now playing")
        .set_footer(
            f"📨 {req.display_name}",
            icon=req.display_avatar_url,
        )
        .set_thumbnail(thumb)
    )

    await say(ctx, hidden=True, embed=embed)


# /search


with_se_cmd_check_and_connect_vc = with_cmd_composer(
    Binds.CONNECT_VC, Checks.CONN | Checks.SPEAK
)


@with_annotated_args
@with_se_cmd_check_and_connect_vc(C.SEARCH)
# -
@tj.as_message_command('search', 'se', 'f', 'yt', 'youtube')
@tj.as_slash_command(
    'search',
    "Searches for tracks on youtube from your query and lets you hear a part of it",
)
async def search_(
    ctx: EitherContext,
    lvc: al.Injected[lv.Lavalink],
    query: t.Annotated[ja.Greedy[ja.Str], "What to be queried?"],
):
    """Searches for tracks on youtube from your query and lets you hear a part of it"""

    await _search(ctx, query, lvc)


@with_se_cmd_check_and_connect_vc(C.SEARCH)
@tj.as_message_menu('Search this song up')
async def search_c(
    ctx: tj.abc.MenuContext,
    lvc: al.Injected[lv.Lavalink],
    msg: hk.Message,
) -> None:
    if not (cnt := extract_content(msg)):
        await err_say(ctx, content="❌ Cannot process an empty message")
        return
    await _search(ctx, cnt, lvc)


async def _search(ctx: EitherContext, query: str, lvc: lv.Lavalink) -> Result[None]:
    from ..lib.music import play, add_tracks_

    erf = ctx.client.get_type_dependency(EmojiRefs)
    assert ctx.guild_id and not isinstance(erf, al.abc.Undefined)

    query = query.strip("<>|")

    QUERIED_N = 10
    PREVIEW_START = 50_000
    PREVIEW_TIME = 30_000

    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert not isinstance(bot, al.abc.Undefined)

    async with trigger_thinking(ctx):
        results = await lvc.auto_search_tracks(query)
    if results.load_type in {'TRACK_LOADED', 'PLAYLIST_LOADED'}:
        play_r = get_full_cmd_repr_from_identifier(C.PLAY, ctx)

        await play(ctx, lvc, tracks=results, respond=True)
        await say(
            ctx,
            hidden=True,
            follow_up=True,
            content=f"💡 This is already a song link. *Did you mean to use {play_r} instead?*",
        )
        return

    queried = results.tracks
    if not queried:
        raise QueryEmpty(query)

    queried_msg = "```css\n%s\n```" % (
        "\n".join(
            f"{i: >2}. {to_stamp(t.info.length):>9} | {wr(t.info.title, 48)}"
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
    msg = await say(
        ctx,
        follow_up=True,
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
        selected: Option[str] = None
        sel_msg: Option[hk.Message] = None

        if not await on_going_tracks():
            await stop(ctx, lvc)

        async for event in stream:
            inter = t.cast(hk.ComponentInteraction, event.interaction)
            key = inter.custom_id

            if key == 'cancel':
                if not await on_going_tracks():
                    await lvc.stop(
                        ctx.guild_id,
                    )
                del_l = {msg}
                if sel_msg:
                    del_l.add(sel_msg)
                await ch.delete_messages(*del_l)
                if not prior_stop:
                    await unstop(ctx, lvc)
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
                    sel_msg = await say(
                        inter,
                        ensure_result=True,
                        content=f"👆 Selected track **`{key}`** `({track.info.title})`",
                    )
                    continue

                await lvc.play(ctx.guild_id, track).start_time_millis(
                    PREVIEW_START
                ).finish_time_millis(PREVIEW_START + PREVIEW_TIME).replace(True).start()

                sel_msg = await say(
                    inter,
                    ensure_result=True,
                    content=f"🎧 Playing a preview of **`{key}`** `({track.info.title})`",
                    delete_after=PREVIEW_TIME / 1000,
                )
                continue

            if selected is None:
                await err_say(inter, content=f"❗ No tracks has been selected yet")
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
                    await unstop(ctx, lvc)
                async with access_queue(ctx, lvc) as q:
                    await add_tracks_(
                        ctx,
                        lvc,
                        selected_t,
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
                await say(
                    inter, hidden=True, content=f"🌐 Link is {selected_t.info.uri}"
                )
            else:
                raise NotImplementedError

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, *components),)
        )
        if not prior_stop:
            await unstop(ctx, lvc)


# /queue


with_q_cmd_check = with_cmd_checks(Checks.QUEUE | Checks.CONN)


@with_q_cmd_check(C.QUEUE)
# -
@tj.as_slash_command('queue', "Lists out the entire queue")
@tj.as_message_command('queue', 'q', 'all')
async def queue_(
    ctx: tj.abc.Context,
    lvc: al.Injected[lv.Lavalink],
):
    q = await get_queue(ctx, lvc)
    pages = await generate_queue_embeds(ctx, lvc)
    pages_n = len(pages)

    erf = ctx.client.get_type_dependency(EmojiRefs)
    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    assert not isinstance(bot, al.abc.Undefined) and not isinstance(
        erf, al.abc.Undefined
    )

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

    _i_ori = (q.pos - 2) // Q_CHUNK + 1
    i = _i_ori

    def _update_buttons(b: hk.api.ButtonBuilder[hk.api.ActionRowBuilder]):
        return (
            (not pages[:i] and b.emoji == '◀️')
            or (not pages[i + 1 :] and b.emoji == '▶️')
            or (i == 0 and b.emoji == '⏪')
            or (i == pages_n - 1 and b.emoji == '⏩')
        )

    embed = pages[i].set_author(name=f"Page {i+1}/{pages_n}")
    msg: hk.Message = await say(
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
            inter = t.cast(hk.ComponentInteraction, event.interaction)
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


# /lyrics


@with_annotated_args
@with_identifier(C.LYRICS)
# -
@tj.as_slash_command('lyrics', 'Attempts to find the lyrics of the current song')
@tj.as_message_command('lyrics', 'ly')
async def lyrics_(
    ctx: EitherContext,
    lvc: al.Injected[lv.Lavalink],
    song: t.Annotated[
        Option[ja.Greedy[ja.Str]], "What song? (If not given, the current song)"
    ] = None,
):
    """Attempts to find the lyrics of the current song"""

    bot = ctx.client.get_type_dependency(hk.GatewayBot)
    erf = ctx.client.get_type_dependency(EmojiRefs)
    assert not isinstance(bot, al.abc.Undefined) and not isinstance(
        erf, al.abc.Undefined
    )

    if song is None:
        if not ((q := await get_queue(ctx, lvc)) and (np := q.current)):
            await err_say(
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
        await err_say(ctx, content=f"❓ Could not find any lyrics for the song")
        return

    for source in lyrics:
        (
            ly_sel.add_option(source, source)
            .set_emoji(erf[source.casefold()])
            .set_description(f"The lyrics fetched from {source}")
            .add_to_menu()
        )

    icons: tuple[str] = (*(erf[source.casefold()].url for source in lyrics),)

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
    msg = await say(
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
        _last_sel: Option[str] = None
        async for event in stream:
            inter = t.cast(hk.ComponentInteraction, event.interaction)
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
