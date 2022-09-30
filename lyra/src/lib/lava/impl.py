import asyncio
import logging

import hikari as hk
import alluka as al
import lavasnek_rs as lv

from ..extras import Panic, lgfmt
from ..dataimpl import LyraDBClientType, LyraDBCollectionType
from ..errors import QueueEmptyError
from ..utils import EmojiRefs, get_client
from ..playback import while_stop, skip
from .utils import (
    BaseEventHandler,
    RepeatMode,
    access_data,
    generate_nowplaying_embed,
    get_data,
    get_repeat_emoji,
    wait_until_current_track_valid,
)
from .events import TrackStoppedEvent


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


class EventHandler(BaseEventHandler):
    def __new__(cls):
        logger.info("Connected to Lavalink Server")
        return super().__new__(cls)

    async def track_start(
        self,
        lvc: lv.Lavalink,
        event: lv.TrackStart,
        /,
    ) -> None:
        t = (await lvc.decode_track(event.track)).title

        if not await lvc.get_guild_node(event.guild_id):
            return
        async with access_data(event.guild_id, lvc) as d:
            q = d.queue
            l = len(d.queue)
            if q.is_stopped:
                return
            q.update_curr_t_started()
            logger.debug(
                f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] started: '{t}'"
            )

            client = get_client()

            cfg = client.get_type_dependency(LyraDBCollectionType)
            erf = client.get_type_dependency(EmojiRefs)

            assert not isinstance(cfg, al.abc.Undefined) and not isinstance(
                erf, al.abc.Undefined
            )

            g_cfg = cfg.find_one({'id': str(event.guild_id)})
            assert g_cfg

            if not g_cfg.setdefault('send_nowplaying_msg', False):
                return

            ch = d.out_channel_id
            assert ch and client.cache
            if not d.queue.current:
                return
            embed = await generate_nowplaying_embed(event.guild_id, client.cache, lvc)
            controls = (
                client.rest.build_action_row()
                .add_button(hk.ButtonStyle.SECONDARY, 'lyra_shuffle')
                .set_emoji(erf['shuffle_b'])
                .add_to_container()
                .add_button(hk.ButtonStyle.SECONDARY, 'lyra_previous')
                .set_emoji(erf['previous_b'])
                .add_to_container()
                .add_button(hk.ButtonStyle.PRIMARY, 'lyra_playpause')
                .set_emoji(erf['resume_b'])
                .add_to_container()
                .add_button(hk.ButtonStyle.SECONDARY, 'lyra_skip')
                .set_emoji(erf['skip_b'])
                .add_to_container()
                .add_button(hk.ButtonStyle.SUCCESS, 'lyra_repeat')
                .set_emoji(get_repeat_emoji(q))
                .add_to_container()
            )

            d.nowplaying_components = components = (controls,)
            d.nowplaying_msg = await client.rest.create_message(
                ch, embed=embed, components=components
            )

            # await asyncio.sleep(1)
            # await skip__(event.guild_id, lvc)

    async def track_finish(self, lvc: lv.Lavalink, event: lv.TrackFinish, /) -> None:
        t = (await lvc.decode_track(event.track)).title
        if not await lvc.get_guild_node(event.guild_id):
            return
        async with access_data(event.guild_id, lvc) as d:
            q = d.queue
            l = len(q)

            client = get_client()

            cfg = client.get_type_dependency(LyraDBCollectionType)
            bot = client.get_type_dependency(hk.GatewayBot)
            assert not isinstance(cfg, al.abc.Undefined) and not isinstance(
                bot, al.abc.Undefined
            )

            g_cfg = cfg.find_one({'id': str(event.guild_id)})
            assert g_cfg

            if g_cfg.get('send_nowplaying_msg', False) and (msg := d.nowplaying_msg):
                ch = d.out_channel_id
                assert ch
                try:
                    await client.rest.delete_messages(ch, msg)
                finally:
                    d.nowplaying_msg = d.nowplaying_components = None

            if q.is_stopped:
                logger.info(
                    f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] stopped: '{t}'"
                )
                bot.dispatch(TrackStoppedEvent(bot))
                return
            try:
                if next_t := q.next:
                    await lvc.play(event.guild_id, next_t.track).start()
                rep = q.repeat_mode
                if rep is RepeatMode.ALL:
                    q.adv()
                    q.wrap()
                elif rep is RepeatMode.NONE:
                    q.adv()
            except QueueEmptyError:
                return
            finally:
                logger.debug(
                    f"In guild {event.guild_id} track [{q.pos: >3}/{l: >3}] ended  : '{t}'"
                )

    async def track_exception(
        self, lvc: lv.Lavalink, event: lv.TrackException, /
    ) -> Panic[None]:
        t_info = await lvc.decode_track(event.track)
        d = await get_data(event.guild_id, lvc)
        l = len(d.queue)

        txt = f"In guild {event.guild_id} track [{d.queue.pos: >3}/{l: >3}] {{0}}: '{t_info.title}'\n\t{event.exception_message}\n\tCaused by: {event.exception_cause}"

        exc_sev = event.exception_severity
        if exc_sev == 'COMMON':
            logger.warning(txt.format('inaccessible'))
        elif exc_sev == 'SUSPICIOUS':
            logger.error(txt.format('malformed'))
        elif exc_sev == 'FAULT':
            logger.critical(txt.format('corrupted'))
        else:
            raise NotImplementedError

        client = get_client()

        mgc = client.get_type_dependency(LyraDBClientType)
        assert not isinstance(mgc, al.abc.Undefined)

        upt = mgc.get_database(  # pyright: ignore [reportUnknownMemberType]
            'internal'
        ).get_collection('unplayable-tracks')
        flt = {'identifier': t_info.identifier}

        if not await lvc.get_guild_node(event.guild_id):
            return
        async with access_data(event.guild_id, lvc) as d:
            async with while_stop(event.guild_id, lvc, d):
                await skip(
                    event.guild_id,
                    lvc,
                    advance=False,
                    change_stop=False,
                )
            if d.queue.next:
                f = asyncio.Task(wait_until_current_track_valid(event.guild_id, lvc))
                await asyncio.wait_for(f, None)

            d.queue.filter_sub(lambda t: t.track.info.identifier == t_info.identifier)
            if not upt.find_one(flt):
                upt.insert_one(flt)  # pyright: ignore [reportUnknownMemberType]

            ch = d.out_channel_id
            msg = d.nowplaying_msg

            try:
                if ch and msg:
                    await client.rest.delete_messages(ch, msg)
            finally:
                d.nowplaying_msg = d.nowplaying_components = None
            ch = d.out_channel_id
            assert ch
            await client.rest.create_message(
                ch, f"💔**`ー`** ~~`{t_info.title}`~~ `(Error playing this track)`"
            )
