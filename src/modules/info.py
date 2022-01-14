from src.lib.music import *


info = tj.Component(checks=(guild_c,), hooks=music_h)


# Now Playing


@info.with_slash_command
@tj.as_slash_command('now-playing', "Displays info of the current track")
async def nowplaying_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await nowplaying_(ctx, lvc=lvc)


@info.with_message_command
@tj.as_message_command('nowplaying', 'now-playing', 'np')
async def nowplaying_m(
    ctx: tj.abc.MessageContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Displays info on the currently playing song."""
    await nowplaying_(ctx, lvc=lvc)


@check(Checks.CONN | Checks.QUEUE | Checks.PLAYING)
async def nowplaying_(ctx: tj.abc.Context, lvc: lv.Lavalink) -> None:
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
                color=0x3C9C9E,
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
        await hid_reply(ctx, embed=embed)
    else:
        await err_reply(ctx, content="❗ Nothing is playing at the moment")
        return


# Search


@info.with_message_command
@tj.with_greedy_argument('query')
@tj.with_parser
@tj.as_message_command('search', 'se', 'f', 'yt')
async def search_m(
    ctx: tj.abc.MessageContext,
    query: str,
    bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    await search_(ctx, query, bot, lvc=lvc)


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
    await search_(ctx, query, bot, lvc=lvc)


@attempt_to_connect
@trigger_thinking()
@check(Checks.CONN)
async def search_(
    ctx: tj.abc.Context, query: str, bot: hk.GatewayBot, lvc: lv.Lavalink
) -> None:
    assert ctx.guild_id is not None
    query = query.strip("<>|")

    QUERIED_N = 5
    PREVIEW_START = 50_000
    PREVIEW_TIME = 30_000

    _queried = await lvc.auto_search_tracks(query)
    if _queried.load_type in ('TRACK_LOADED', 'PLAYLIST_LOADED'):
        await play__(ctx, lvc, tracks=_queried, respond=True)
        await hid_reply(
            ctx,
            content="💡 It is best to input a search query to the `/search` command. *For links, use `/play` instead*",
        )
        return

    queried = _queried.tracks
    if not queried:
        raise QueryEmpty

    queried_msg = "```css\n%s\n```" % (
        "\n".join(
            f"{i: >2}. {ms_stamp(t.info.length):>9} | {wrap(t.info.title, 48)}"
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
    msg = await def_reply(
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
                    await hid_reply(ctx, content=f"🌐 Link is <{selected_t.info.uri}>")
                case _:
                    raise NotImplementedError

        await ctx.edit_initial_response(
            components=(*disable_buttons(ctx.rest, pre_row, ops_row),)
        )
        if not prior_stop:
            await continue__(ctx, lvc)


# Queue


@info.with_slash_command
@tj.as_slash_command('queue', "Lists out the entire queue")
async def queue_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await queue_(ctx, lvc=lvc)


@info.with_message_command
@tj.as_message_command('queue', 'q')
async def queue_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await queue_(ctx, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN)
async def queue_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert not ((ctx.guild_id is None) or (ctx.cache is None))
    q = await get_queue(ctx, lvc)
    if np := q.current:
        np_info = np.track.info
        req = ctx.cache.get_member(ctx.guild_id, np.requester)
        assert req is not None
        np_text = f"```css\n{q.pos+1: >2}. {ms_stamp(np_info.length):>9} | {wrap(np_info.title, 48)}\n\t\t\t\t[{req.display_name}]\n```"
    else:
        np_text = f"```css\n{'---':^63}\n```"

    queue_durr = sum(t.track.info.length for t in q)
    queue_elapsed = sum(t.track.info.length for t in q.history) + (q.np_position or 0)
    queue_eta = queue_durr - queue_elapsed

    prev = None if not (his := q.history) else his[0]

    desc = (
        ""
        if q.repeat_mode is RepeatMode.NONE
        else (
            "**```diff\n+| Repeating this entire queue\n```**"
            if q.repeat_mode is RepeatMode.ALL
            else "***```diff\n-| Repeating the current track\n```***"
        )
    )

    embed = (
        hk.Embed(
            title="📀 Queue",
            description=desc,
            color=0xFDEDA1,
        )
        .add_field(
            "Now playing",
            np_text,
        )
        .add_field(
            "Next up",
            f"```{'brainfuck' if q.repeat_mode is RepeatMode.ONE else 'css'}\n%s\n```"
            % (
                "\n".join(
                    f"{i+2: >2}․ {ms_stamp(t_.track.info.length):>9} | {wrap(t_.track.info.title, 48)}"
                    for i, t_ in enumerate(q.upcoming[:15], q.pos)
                )
                or f"{'---':^63}",
            ),
        )
        .add_field(
            "Previous",
            f"`{q.pos: >2}․ {ms_stamp(prev.track.info.length):>9} | {wrap(prev.track.info.title, 48)}`"
            if prev
            else f"```\n{'---':^63}\n```",
        )
        .set_footer(
            f"Queue Duration: {ms_stamp(queue_elapsed)} / {ms_stamp(queue_durr)}"
        )
    )

    await hid_reply(ctx, embed=embed)


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
):
    await lyrics_(ctx, song, lvc=lvc)


@info.with_message_command
@tj.with_greedy_argument('song', default=None)
@tj.with_parser
@tj.as_message_command('lyrics', 'ly')
async def lyrics_m(
    ctx: tj.abc.MessageContext,
    song: t.Optional[str],
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
):
    """
    Attempts to find the lyrics of the current song
    """
    await lyrics_(ctx, song, lvc=lvc)


@trigger_thinking(hk.MessageFlag.EPHEMERAL)
@check(Checks.CATCH_ALL)
async def lyrics_(ctx: tj.abc.Context, song: t.Optional[str], lvc: lv.Lavalink) -> None:
    """
    Attempts to find the lyrics of the current song
    """
    ...
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
    try:
        lyrics_data = await get_lyrics(song)

        if lyrics_data.link:
            return await hid_reply(ctx, content=f"🎤 Lyrics Link: <{lyrics_data.link}>")

        assert (
            lyrics_data.title
            and lyrics_data.lyrics
            and lyrics_data.author
            and lyrics_data.thumbnail
        )

        embed = hk.Embed(
            title='🎤 ' + lyrics_data.title,
            description=lyrics_data.lyrics,
        )
        embed.set_thumbnail(lyrics_data.thumbnail)
        embed.set_author(name=lyrics_data.author)
        embed.set_footer(lyrics_data.source)
        await def_reply(ctx, embed=embed)

    except LyricsNotFound:
        await err_reply(ctx, content=f"❓ Could not find any lyrics for the song")
        return

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
