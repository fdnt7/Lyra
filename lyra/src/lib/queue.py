import typing as t
import logging
import difflib as dfflib

import tanjun as tj
import alluka as al
import lavasnek_rs as lv

from .utils import (
    ButtonBuilderType,
    ContextishType,
    AnyContextType,
    edit_components,
    err_say,
    get_rest,
    say,
    trigger_thinking,
)
from .consts import ADD_TRACKS_WRAP_LIM
from .extras import (
    NULL,
    IterableOr,
    Option,
    Result,
    Panic,
    url_regex,
    lgfmt,
    join_and,
)
from .errors import (
    Argument,
    IllegalArgument,
    InvalidArgument,
    NoPlayableTracks,
    OthersInVoice,
    PlaybackChangeRefused,
)
from .cmd.compose import others_not_in_vc_check
from .lava.utils import (
    QueueList,
    RepeatMode,
    Trackish,
    repeat_emojis,
    access_data,
    access_queue,
    get_data,
    set_data,
)
from .playback import back, skip, while_stop, set_pause
from .dataimpl import LyraDBClientType


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


async def to_tracks(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    value: str,
    *,
    source: Option[str] = None,
) -> Panic[tuple[Trackish, ...]]:
    if source is None:
        source = 'yt'
    tracks: list[Trackish] = []
    errors: list[ValueError] = []
    songs = (*map(lambda s: s.strip("<>|"), value.split(' | ')),)
    async with trigger_thinking(t.cast(AnyContextType, ctx)):
        for song in songs:
            query = (
                song if url_regex.fullmatch(song) else '%ssearch:%s' % (source, song)
            )
            query = await lvc.get_tracks(query)
            if not query.tracks:
                errors.append(ValueError(song))
                continue
            if query.load_type == 'PLAYLIST_LOADED':
                tracks.append(query)
                continue
            tracks.append(query.tracks[0])
    if errors:
        raise tj.ConversionError('Some query returns no results', value, errors)
    return (*tracks,)


async def play(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    tracks: IterableOr[Trackish],
    *,
    respond: bool = False,
    shuffle: bool = False,
) -> None:
    assert ctx.guild_id
    async with access_queue(ctx, lvc) as q:
        await add_tracks_(
            ctx,
            lvc,
            tracks,
            q,
            respond=respond,
            shuffle=shuffle,
        )


async def add_tracks_(
    ctx: tj.abc.Context,
    lvc: lv.Lavalink,
    /,
    tracks_: IterableOr[Trackish],
    queue: QueueList,
    *,
    respond: bool = False,
    shuffle: bool = False,
    ignore_stop: bool = False,
) -> Result[tuple[lv.Track, ...]]:
    assert ctx.guild_id
    flttn_t: t.Iterable[lv.Track] = []
    if isinstance(tracks_, Trackish):
        tracks_ = (tracks_,)
    for t_ in tracks_:
        if isinstance(t_, lv.Tracks):
            flttn_t.extend(t_.tracks)
            continue
        flttn_t.append(t_)

    mgc = ctx.get_type_dependency(LyraDBClientType)
    assert not isinstance(mgc, al.abc.Undefined)

    upt = mgc.get_database(  # pyright: ignore [reportUnknownMemberType]
        'internal'
    ).get_collection('unplayable-tracks')
    upt_: set[str] = {_upt['identifier'] for _upt in upt.find()}

    safe_flttn_t = (*(t_ for t_ in flttn_t if t_.info.identifier not in upt_),)
    if not safe_flttn_t:
        raise NoPlayableTracks

    players = (
        *(
            lvc.play(ctx.guild_id, t_).requester(ctx.author.id).replace(False)
            for t_ in safe_flttn_t
        ),
    )
    queue.ext(*map(lambda p: p.to_track_queue(), players))

    if respond:
        playlists = frozenset(t_ for t_ in tracks_ if isinstance(t_, lv.Tracks))
        sgl_tracks = frozenset(t_ for t_ in tracks_ if isinstance(t_, lv.Track))

        shuffle_txt = "🔀%s and shuffled the queue" if shuffle else "%s to the queue"
        if (len_t := len(sgl_tracks)) > ADD_TRACKS_WRAP_LIM:
            sgl_track_txt = f"`{len(sgl_tracks)} tracks`"
        elif len_t > 0:
            sgl_track_txt = join_and(f'`{t_.info.title}`' for t_ in sgl_tracks)
        else:
            sgl_track_txt = ""

        if (len_p := len(playlists)) > ADD_TRACKS_WRAP_LIM:
            playlist_txt = f"`{sum(map(lambda p: len(p.tracks), playlists))} tracks` in total from `{len_p} playlists`"
        elif len_p > 0:
            playlist_txt = join_and(
                f"`{len(p.tracks)} tracks` from playlist `{p.playlist_info.name}`"
                for p in playlists
            )
        else:
            playlist_txt = ""

        enqueued_txt = join_and((sgl_track_txt, playlist_txt))
        plus_e = "**`＋`**" if len(safe_flttn_t) <= 1 else "**`≡+`**"
        txt = shuffle_txt % (f"{plus_e} Added {enqueued_txt}")
        await say(ctx, follow_up=True, content=txt)

        if (diff := (len(flttn_t) - len(safe_flttn_t))) >= 1:
            await say(
                ctx,
                follow_up=True,
                hidden=True,
                content=f"💔 Skipped `{diff}` unplayable track(s)",
            )

    first = players[0]
    if not queue.is_stopped or ignore_stop:
        await first.start()
    if shuffle:
        queue.shuffle()

    return (*safe_flttn_t,)


async def remove_track(
    ctx: tj.abc.Context, track: Option[str], lvc: lv.Lavalink, /
) -> Result[lv.TrackQueue]:
    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    np = q.current
    if track is None:
        if not np:
            raise InvalidArgument(Argument(track, None))
        rm = np
        i = q.pos
    elif track.isdigit():
        t = int(track)
        if not (1 <= t <= len(q)):
            raise IllegalArgument(Argument(t, (1, len(q))))
        i = t - 1
        rm = q[i]
    else:
        rm = max(
            q,
            key=lambda t: dfflib.SequenceMatcher(
                None, t.track.info.title, track
            ).ratio(),
        )
        i = q.index(rm)

    try:
        await others_not_in_vc_check(ctx, lvc)
    except OthersInVoice:
        if rm.requester != ctx.author.id:
            raise PlaybackChangeRefused

    if rm == np:
        async with while_stop(ctx, lvc, d):
            await skip(ctx, lvc, advance=False, reset_repeat=True, change_stop=False)

    if i < q.pos:
        q.pos = max(0, q.pos - 1)
    q.sub(rm)

    logger.info(
        f"In guild {ctx.guild_id} track [{i: >3}/{len(q): >3}] removed: '{rm.track.info.title}'"
    )

    await set_data(ctx.guild_id, lvc, d)
    return rm


async def remove_tracks(
    ctx: tj.abc.Context, start: int, end: int, lvc: lv.Lavalink, /
) -> Result[list[lv.TrackQueue]]:
    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    if not (1 <= start <= end <= len(q)):
        raise IllegalArgument(Argument((start, end), (1, len(q))))

    i_s = start - 1
    i_e = end - 1
    # t_n = end - i_s
    rm = q[i_s:end]
    if q.current in rm:
        q.reset_repeat()
        async with while_stop(ctx, lvc, d):
            if next_t := None if len(q) <= end else q[end]:
                await set_pause(ctx, lvc, pause=False)
                await lvc.play(ctx.guild_id, next_t.track).start()
    if i_s < q.pos:
        q.pos = max(0, i_s + (q.pos - i_e - 1))
    q.sub(*rm)

    logger.info(
        f"""In guild {ctx.guild_id} tracks [{i_s: >3}~{i_e: >3}/{len(q): >3}] removed: '{', '.join(("'%s'" %  t.track.info.title) for t in rm)}'"""
    )

    await set_data(ctx.guild_id, lvc, d)
    return rm


async def shuffle_abs(ctx_: ContextishType, lvc: lv.Lavalink):
    async with access_queue(ctx_, lvc) as q:
        if not q.upcoming:
            await err_say(ctx_, content=f"❗ This is the end of the queue")
            return
        q.shuffle()

        await say(
            ctx_,
            show_author=True,
            content=f"🔀 Shuffled the upcoming tracks. `(Track #{q.pos+2}-{len(q)}; {len(q) - q.pos - 1} tracks)`",
        )


async def insert_track(
    ctx: tj.abc.Context, insert: int, track: Option[int], lvc: lv.Lavalink, /
) -> Result[lv.TrackQueue]:
    assert ctx.guild_id

    d = await get_data(ctx.guild_id, lvc)
    q = d.queue
    np = q.current
    p_ = q.pos
    if track is None:
        if not np:
            raise InvalidArgument(Argument(np, track))
        t_ = p_
        ins = np
    else:
        t_ = track - 1
        ins = q[t_]

    i_ = insert - 1
    if t_ in {i_, insert}:
        raise ValueError
    if not ((0 <= t_ < len(q)) and (0 <= i_ < len(q))):
        raise IllegalArgument(Argument((track, insert), (1, len(q))))

    if t_ < p_ <= i_:
        q.decr()
    elif i_ < p_ < t_:
        q.adv()

    elif i_ < p_ == t_:
        await back(ctx, lvc, advance=False, reset_repeat=True)

    elif p_ == t_ < i_:
        async with while_stop(ctx, lvc, d):
            await skip(ctx, lvc, advance=False, reset_repeat=True, change_stop=False)

    q[t_] = t.cast(lv.TrackQueue, NULL)
    q.insert(insert, ins)
    q.remove(t.cast(lv.TrackQueue, NULL))

    await set_data(ctx.guild_id, lvc, d)
    return ins


async def repeat_abs(
    ctx_: ContextishType,
    mode: Option[RepeatMode],
    lvc: lv.Lavalink,
) -> Panic[None]:
    """Select a repeat mode for the queue"""
    async with access_data(ctx_, lvc) as d:
        q = d.queue
        if mode is None:
            modes = (*RepeatMode,)
            mode = modes[(modes.index(q.repeat_mode) + 1) % 3]
        assert mode
        q.set_repeat(mode)

    if mode is RepeatMode.NONE:
        msg = "Disabled repeat"
        e = '➡️'
    elif mode is RepeatMode.ALL:
        msg = "Repeating the entire queue"
        e = '🔁'
    else:
        msg = "Repeating only this current track"
        e = '🔂'

    from .lava.utils import get_repeat_emoji

    await say(ctx_, show_author=True, content=f"{e} {msg}")
    if d.nowplaying_msg:
        rest = get_rest(ctx_)

        edits: t.Callable[
            [ButtonBuilderType], ButtonBuilderType
        ] = lambda x: x.set_emoji(get_repeat_emoji(q))
        predicates: t.Callable[[ButtonBuilderType], bool] = (
            lambda x: x.emoji in repeat_emojis
        )

        assert d.nowplaying_components
        components = edit_components(
            rest,
            *d.nowplaying_components,
            edits=edits,
            predicates=predicates,
        )

        await d.edit_now_playing_components(rest, components)
