from src.lib.music import *
from src.lib.checks import Checks, check


info = tj.Component(name='Info').add_check(guild_c).set_hooks(music_h)


# Ping


@info.with_slash_command
@tj.as_slash_command('ping', "Shows the bot's latency")
async def ping_s(ctx: tj.abc.SlashContext):
    await ping_(ctx)


@info.with_message_command
@tj.as_message_command('ping', 'latency', 'pi', 'lat', 'late', 'png')
async def ping_m(ctx: tj.abc.MessageContext):
    """
    Shows the bot's latency
    """
    await ping_(ctx)


async def ping_(ctx: tj.abc.Context, /) -> None:
    """Shows the bot's latency"""

    assert ctx.shards
    await reply(ctx, content=f"📶 **{int(ctx.shards.heartbeat_latency*1000)}** ms")


# Now Playing


@info.with_slash_command
@tj.as_slash_command('now-playing', "Displays info of the current track")
async def nowplaying_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await nowplaying_(ctx, lvc=lvc)


@info.with_message_command
@tj.as_message_command(
    'nowplaying', 'now-playing', 'np', 'now', 'curr', 'current', 'crr'
)
async def nowplaying_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Displays info on the currently playing song."""
    await nowplaying_(ctx, lvc=lvc)


@check(Checks.CONN | Checks.QUEUE | Checks.PLAYING)
async def nowplaying_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink) -> None:
    """Displays info on the currently playing song."""
    assert not ((ctx.guild_id is None) or (ctx.cache is None) or (ctx.member is None))

    q = await get_queue(ctx, lvc)
    e = '⏹️' if q.is_stopped else ('▶️' if q.is_paused else '⏸️')

    assert q.np_position
    if curr_t := q.current:
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

        embed = (
            hk.Embed(
                title=f"🎶 {t_info.title}",
                description="%s\n\n%s"
                % (
                    f'💿 **{t_info.author}**',
                    f"{e} `{np_pos:─<{padding}}{song_len:─>12}`".replace('─', ' ', 1)[
                        ::-1
                    ]
                    .replace('─', ' ', 1)[::-1]
                    .replace('─', '▬', progress),
                ),
                url=t_info.uri,
                color=(213, 111, 234),
                # timestamp=dt.datetime.now().astimezone(),
            )
            .set_author(name="Now playing")
            .set_footer(
                f"Requested by: {req.display_name}",
                icon=req.avatar_url or ctx.author.default_avatar_url,
            )
            .set_thumbnail(
                f"https://img.youtube.com/vi/{t_info.identifier}/maxresdefault.jpg"
            )
        )
        await reply(ctx, hidden=True, embed=embed)
    else:
        await err_reply(ctx, content="❗ Nothing is playing at the moment")
        return


# Search


@info.with_message_command
@tj.with_greedy_argument('query')
@tj.with_parser
@tj.as_message_command('search', 'se', 'f', 'yt', 'youtube')
async def search_m(
    ctx: tj.abc.MessageContext,
    query: str,
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await search_(ctx, query, bot=bot, lvc=lvc)


@info.with_slash_command
@tj.with_str_slash_option('query', "What to be queried?")
@tj.as_slash_command(
    'search',
    "Searches for tracks on youtube from your query and lets you hear a part of it",
)
async def search_s(
    ctx: tj.abc.SlashContext,
    query: str,
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await search_(ctx, query, bot=bot, lvc=lvc)


@attempt_to_connect
@check(Checks.CONN)
async def search_(
    ctx: tj.abc.Context, query: str, /, *, bot: hk.GatewayBot, lvc: lv.Lavalink
) -> None:
    assert ctx.guild_id is not None
    query = query.strip("<>|")

    QUERIED_N = 5
    PREVIEW_START = 50_000
    PREVIEW_TIME = 30_000

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

    pre_row = ctx.rest.build_action_row()
    ops_row = ctx.rest.build_action_row()
    for i in map(str, range(1, len(queried[:QUERIED_N]) + 1)):
        pre_row.add_button(hk_msg.ButtonStyle.SECONDARY, i).set_label(
            i
        ).add_to_container()

    ops_row.add_button(hk_msg.ButtonStyle.SUCCESS, 'enqueue').set_label(
        "＋ Enqueue"
    ).add_to_container()
    ops_row.add_button(hk_msg.ButtonStyle.PRIMARY, 'link').set_label(
        "Get Link"
    ).add_to_container()
    ops_row.add_button(hk_msg.ButtonStyle.DANGER, 'cancel').set_label(
        "Cancel"
    ).add_to_container()

    embed = hk.Embed(
        title=f"🔎 Searching for `{query}`",
    ).add_field("Search results", value=queried_msg)
    msg = await reply(
        ctx,
        embed=embed,
        components=[pre_row, ops_row],
    )
    ch = await ctx.fetch_channel()

    async def playing() -> bool:
        return bool((q := await get_queue(ctx, lvc)) and q.current)

    prior_stop = (await get_queue(ctx, lvc)).is_stopped

    with bot.stream(hk.InteractionCreateEvent, timeout=TIMEOUT).filter(
        lambda e: isinstance(e.interaction, hk.ComponentInteraction)
        and e.interaction.user == ctx.author
        and e.interaction.message == msg
    ) as stream:
        selected: t.Optional[str] = None
        sel_msg: t.Optional[hk.Message] = None

        if not await playing():
            await stop__(ctx, lvc)

        async for event in stream:
            inter = event.interaction
            assert isinstance(inter, hk.ComponentInteraction)
            await inter.create_initial_response(
                hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
            )
            key = inter.custom_id

            if key == 'cancel':
                if not await playing():
                    await lvc.stop(
                        ctx.guild_id,
                    )
                await ctx.delete_initial_response()
                if sel_msg:
                    await ch.delete_messages(sel_msg)
                if not prior_stop:
                    await continue__(ctx, lvc)
                return

            if key in map(str, range(1, QUERIED_N + 1)):
                track = queried[int(key) - 1]
                if sel_msg:
                    await ch.delete_messages(sel_msg)

                selected = key

                if await playing():
                    sel_msg = await reply(
                        ctx,
                        content=f"👆 Selected track **`{key}`** `({track.info.title})`",
                    )
                    continue

                # prev_start = PREVIEW_START
                # prev_time = PREVIEW_TIME

                sel_msg = await reply(
                    ctx,
                    content=f"🎶 Playing a preview of **`{key}`** `({track.info.title})`",
                    delete_after=PREVIEW_TIME / 1000,
                )
                await lvc.play(ctx.guild_id, track).start_time_millis(
                    PREVIEW_START
                ).finish_time_millis(PREVIEW_START + PREVIEW_TIME).replace(True).start()
                continue

            if selected is None:
                await err_reply(ctx, content=f"❗ No tracks has been selected yet")
                continue
            selected_t = queried[int(selected) - 1]
            assert sel_msg is not None
            match key:
                case 'enqueue':
                    if not await playing():
                        await lvc.stop(
                            ctx.guild_id,
                        )
                    async with access_queue(ctx, lvc) as q:
                        await enqueue_track__(
                            ctx,
                            lvc,
                            track=selected_t,
                            queue=q,
                            respond=False,
                            ignore_stop=True,
                        )
                    await ctx.edit_initial_response(
                        f"**🔎`＋`** Added `{selected_t.info.title}` to the queue",
                        embed=None,
                        user_mentions=False,
                        components=[],
                    )
                    await ch.delete_messages(sel_msg)
                    if not prior_stop:
                        await continue__(ctx, lvc)
                    return
                case 'link':
                    await reply(
                        ctx, hidden=True, content=f"🌐 Link is <{selected_t.info.uri}>"
                    )
                case _:
                    raise NotImplementedError

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, pre_row, ops_row),)
        )
        if not prior_stop:
            await continue__(ctx, lvc)


# Queue


@info.with_slash_command
@tj.as_slash_command('queue', "Lists out the entire queue")
async def queue_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
):
    await queue_(ctx, lvc=lvc, bot=bot)


@info.with_message_command
@tj.as_message_command('queue', 'q', 'all')
async def queue_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
):
    await queue_(ctx, lvc=lvc, bot=bot)


@check(Checks.QUEUE | Checks.CONN)
async def queue_(ctx: tj.abc.Context, /, *, lvc: lv.Lavalink, bot: hk.GatewayBot):
    q = await get_queue(ctx, lvc)
    pages = await generate_queue_embeds__(ctx, lvc)
    pages_n = len(pages)

    def _page_row(*, cancel_b: bool = False):
        row = ctx.rest.build_action_row()

        row.add_button(hk_msg.ButtonStyle.SECONDARY, 'start').set_emoji(
            '⏪'
        ).add_to_container()

        row.add_button(hk_msg.ButtonStyle.SECONDARY, 'prev').set_emoji(
            '◀️'
        ).add_to_container()

        if cancel_b:
            _3rd_b = row.add_button(hk_msg.ButtonStyle.DANGER, 'delete').set_emoji(
                c.WHITE_CROSS
            )
        else:
            _3rd_b = row.add_button(hk_msg.ButtonStyle.PRIMARY, 'main').set_emoji('⏺️')
        _3rd_b.add_to_container()

        row.add_button(hk_msg.ButtonStyle.SECONDARY, 'next').set_emoji(
            '▶️'
        ).add_to_container()

        row.add_button(hk_msg.ButtonStyle.SECONDARY, 'end').set_emoji(
            '⏩'
        ).add_to_container()

        return row

    _i_ori = (q.pos - 2) // FIELD_SLICE + 1
    i = _i_ori

    def _update_buttons(b: DisableableComponentsType):
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

            match key:
                case 'main':
                    i = _i_ori
                case 'next':
                    i += 1
                case 'prev':
                    i -= 1
                case 'start':
                    i = 0
                case 'end':
                    i = pages_n - 1
                case 'delete':
                    await ctx.delete_initial_response()
                    return

            _row = _page_row(cancel_b=i == _i_ori)
            embed = pages[i].set_author(name=f"Page {i+1}/{pages_n}")

            await ctx.edit_initial_response(
                embed=embed,
                components=(
                    *disable_components(ctx.rest, _row, predicates=_update_buttons),
                ),
            )

        await ctx.edit_initial_response(
            components=(*disable_components(ctx.rest, _row),)
        )


# Lyrics


@info.with_slash_command
@tj.with_str_slash_option(
    'song', "What song? (If not given, the current song)", default=None
)
@tj.as_slash_command('lyrics', 'Attempts to find the lyrics of the current song')
async def lyrics_s(
    ctx: tj.abc.SlashContext,
    song: t.Optional[str],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
):
    await lyrics_(ctx, song, lvc=lvc, bot=bot)


@info.with_message_command
@tj.with_greedy_argument('song', default=None)
@tj.with_parser
@tj.as_message_command('lyrics', 'ly')
async def lyrics_m(
    ctx: tj.abc.MessageContext,
    song: t.Optional[str],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
):
    """
    Attempts to find the lyrics of the current song
    """
    await lyrics_(ctx, song, lvc=lvc, bot=bot)


@check(Checks.CATCH_ALL)
async def lyrics_(
    ctx: tj.abc.Context,
    song: t.Optional[str],
    /,
    *,
    lvc: lv.Lavalink,
    bot: hk.GatewayBot,
) -> None:
    """Attempts to find the lyrics of the current song"""
    assert not (ctx.guild_id is None)
    if song is None:
        if not (np := ((await get_queue(ctx, lvc))).current):
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
    cancel_b = act_row.add_button(hk_msg.ButtonStyle.DANGER, 'delete').set_emoji(
        c.WHITE_CROSS
    )

    try:
        async with trigger_thinking(ctx):
            lyrics_data = await get_lyrics(song)
    except LyricsNotFound:
        await err_reply(ctx, content=f"❓ Could not find any lyrics for the song")
        return

    for source in lyrics_data:
        (
            ly_sel.add_option(source, source)
            .set_emoji(eval(f"c.{source.upper()}_EMOJI"))
            .set_description(f"The lyrics fetched from {source}")
            .add_to_menu()
        )

    icons: tuple[str] = tuple(
        eval(f'c.{source.upper()}_ICON') for source in lyrics_data
    )

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
                    else f"{wr(ly.lyrics, 3_996, '...')}\n\n**View full lyrics on:**\n{ly.url}",
                )
            ),
            url=ly.url,
        )
        .set_thumbnail(ly.thumbnail)
        .set_author(name=ly.artist, icon=ly.artist_icon, url=ly.artist_url)
        .set_footer(ly.source, icon=i)
        for ly, i in zip(lyrics_data.values(), icons)
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
                await ctx.delete_initial_response()
                return

            assert sel is not None
            if sel == _last_sel:
                continue
            _last_sel = sel
            await ctx.edit_initial_response(embed=embeds[sel])

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


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(info.copy())
