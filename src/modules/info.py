from src.lib.music import *


music = tj.Component(checks=(guild_c,), hooks=music_h)


# -


# Now Playing


@music.with_slash_command
@tj.as_slash_command("nowplaying", "Displays info of the current track")
async def nowplaying_s(
    ctx: tj.abc.SlashContext,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    await nowplaying_(ctx, lvc=lvc)


@music.with_message_command
@tj.as_message_command("nowplaying", "np")
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

    async with access_queue(ctx, lvc) as q:
        assert q.np_position
        if curr_t := q.now_playing:
            t_info = curr_t.track.info
            req = ctx.cache.get_member(ctx.guild_id, curr_t.requester)
            assert req is not None

            # Info on the current track
            title_pad = int(len(t_info.title) // 1.00)
            username_pad = int(len(ctx.member.display_name) // 0.85)
            padding = min(72, max(title_pad, username_pad))
 
            song_len = ms_stamp(t_info.length)
            np_pos = ms_stamp(q.np_position)
            # Info on the current track
            embed = (
                hk.Embed(
                    title=f"🎶 {t_info.title}",
                    description=f"💿 **{t_info.author}**\n\n`{np_pos: <{padding}}`**`{song_len: >12}`**",
                    url=t_info.uri,
                    color=0x3C9C9E,
                    # timestamp=dt.datetime.now().astimezone(),
                )
                .set_author(name="Now playing")
                .set_footer(
                    f"Requested by: {req.display_name}",
                    icon=req.avatar_url or ctx.author.default_avatar_url,
                )
            )
            await hid_reply(ctx, embed=embed)
        else:
            await err_reply(ctx, content="❗ Nothing is playing at the moment")
            return


# Search


# @music.with_slash_command
# @tj.with_str_slash_option("query", "What to be queried?")
# @tj.as_slash_command(
#     "search",
#     "[IN DEVELOPMENT] Searches for tracks on youtube from your query and lets you hear a clip of it",
# )
# async def search_s(
#     ctx: tj.abc.SlashContext,
#     query: str,
#     bot: hk.GatewayBot = tj.injected(type=hk.GatewayBot),
#     lavalink: lv.Lavalink = tj.injected(type=lv.Lavalink),
# ):
#     await _search(ctx, query, bot, lavalink)


# async def _search(
#     ctx: tj.abc.Context, query: str, bot: hk.GatewayBot, lavalink: lv.Lavalink
# ) -> None:
#     assert ctx.guild_id is not None
#     QUERIED_N = 5
#     PREVIEW_START = 50
#     PREVIEW_TIME = 30
#     queried = (await lavalink.auto_search_tracks(query)).tracks
#     desc = "\n".join(
#         f"**`{i: >2}`**　`{wrap(t.info.title, 40) :<40}` `{ms_stamp(t.info.length): >7}`"
#         for i, t in enumerate(queried[:QUERIED_N], 1)
#     )
#     previews_row = ctx.rest.build_action_row()
#     actions_row = ctx.rest.build_action_row()
#     for i in map(str, range(1, QUERIED_N + 1)):
#         previews_row.add_button(ButtonStyle.SECONDARY, i).set_label(
#             i
#         ).add_to_container()

#     actions_row.add_button(ButtonStyle.SUCCESS, "enqueue").set_label(
#         "＋ Add to queue"
#     ).add_to_container()
#     actions_row.add_button(ButtonStyle.DANGER, "cancel").set_label(
#         "Done"
#     ).add_to_container()

#     embed = hk.Embed(title="🔎 Search results", description=desc)
#     await ctx.edit_initial_response(
#         embed=embed,
#         components=[previews_row, actions_row],
#     )
#     try:
#         async with bot.stream(hk.InteractionCreateEvent, timeout=60).filter(
#             ("interaction.user.id", ctx.author.id)
#         ) as stream:
#             selected: str
#             async for event in stream:
#                 await event.interaction.create_initial_response(
#                     hk.ResponseType.DEFERRED_MESSAGE_UPDATE,
#                 )
#                 key = event.interaction.custom_id
#                 if key in map(str, range(1, QUERIED_N + 1)):
#                     await ctx.edit_initial_response(
#                         content=f"Playing {key}",
#                         embed=embed,
#                         components=[previews_row, actions_row],
#                     )
#                     selected = key
#                     await lavalink.play(
#                         ctx.guild_id, queried[int(key) - 1]
#                     ).start_time_secs(PREVIEW_START).finish_time_secs(
#                         PREVIEW_START + PREVIEW_TIME
#                     ).replace(
#                         True
#                     ).start()
#                 elif key == "enqueue":
#                     await lavalink.play(
#                         ctx.guild_id, queried[int(selected) - 1]
#                     ).queue()
#                     await ctx.edit_initial_response(
#                         content=f"**`＋`** Added `{queried[int(selected)-1].info.title}` to the queue",
#                         components=[],
#                         embed=None,
#                     )
#                 elif key == "cancel":
#                     await ctx.edit_initial_response(content=f"Done", components=[])
#                     await lavalink.skip(ctx.guild_id)
#                     return

#     except asyncio.TimeoutError:
#         await ctx.edit_initial_response(content="Timed out", embed=None, components=[])


# Queue


@music.with_slash_command
@tj.as_slash_command("queue", "Lists out the entire queue")
async def queue_s(
    ctx: tj.abc.SlashContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await queue_(ctx, lvc=lvc)


@music.with_message_command
@tj.as_message_command("queue", "q")
async def queue_m(
    ctx: tj.abc.MessageContext, lvc: lv.Lavalink = tj.injected(type=lv.Lavalink)
):
    await queue_(ctx, lvc=lvc)


@check(Checks.QUEUE | Checks.CONN)
async def queue_(ctx: tj.abc.Context, lvc: lv.Lavalink):
    assert not ((ctx.guild_id is None) or (ctx.cache is None))
    async with access_queue(ctx, lvc) as q:
        if np := q.now_playing:
            np_info = np.track.info
            req = ctx.cache.get_member(ctx.guild_id, np.requester)
            assert req is not None
            np_text = f"```css\n{q.pos+1: >2}. {ms_stamp(np_info.length):>9} | {wrap(np_info.title, 48)}\n\t\t\t\t[{req.display_name}]\n```"
        else:
            np_text = f"```css\n{'---':^63}\n```"

        queue_durr = sum(t.track.info.length for t in q)
        queue_elapsed = sum(t.track.info.length for t in q.history) + (
            q.np_position or 0
        )
        queue_eta = queue_durr - queue_elapsed

        prev = None if not (his := q.history) else his[0]

        embed = (
            hk.Embed(
                title="📀 Queue",
                # title="🗒️ Queue",
                color=0xFDEDA1,
                # timestamp=dt.datetime.now().astimezone(),
            )
            .add_field(
                "Now playing",
                # f"```css\n{q.pos+1: >2}. {wrap(np_info.title, 50): <50}{ms_stamp(np_info.length):>9}\n\t[{ctx.member.display_name}]\n```"
                np_text,
            )
            # .add_field(
            #     "Previous",
            #     '\n'.join(
            #         f"`{i+1: >2}. {wrap(q.track.info.title, 50): <50}{ms_stamp(q.track.info.length):>9}`"
            #         for i, q in enumerate(q.history)
            #     )
            #     or '`This is the first track in the queue`',
            # )
            # .add_field(
            #     "Next up",
            #     "```css\n%s\n```"
            #     % (
            #         '\n'.join(
            #             f"{i+2: >2}. {wrap(q.track.info.title, 50): <50}{ms_stamp(q.track.info.length):>9}"
            #             for i, q in enumerate(q.upcoming, q.pos)
            #         )
            #         or 'This is the last track in the queue',
            #     ),
            # )
            .add_field(
                "Next up",
                "```css\n%s\n```"
                % (
                    "\n".join(
                        f"{i+2: >2}. {ms_stamp(q_.track.info.length):>9} | {wrap(q_.track.info.title, 48)}"
                        for i, q_ in enumerate(q.upcoming[:15], q.pos)
                    )
                    or f"{'---':^63}",
                ),
            )
            .add_field(
                "Previous",
                # '\n'.join(
                #     f"`{i+1: >2}. {ms_stamp(q.track.info.length):>9} | {wrap(q.track.info.title, 48)}`"
                #     for i, q in enumerate(q.history)
                # )
                f"`{q.pos: >2}. {ms_stamp(prev.track.info.length):>9} | {wrap(prev.track.info.title, 48)}`"
                if prev
                else f"```\n{'---':^63}\n```",
            )
            .set_footer(
                f"Queue Duration: {ms_stamp(queue_elapsed)} / {ms_stamp(queue_durr)}"
            )
        )

        await hid_reply(ctx, embed=embed)


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(music.copy())
