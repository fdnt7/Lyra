import logging

import hikari as hk
import tanjun as tj
import alluka as al
import lavasnek_rs as lv


from src.lib.music import music_h
from src.lib.utils import guild_c
from src.lib.checks import Checks, check
from src.lib.errors import NotConnected
from src.lib.lavaimpl import get_data
from src.lib.consts import LOG_PAD


control = (
    tj.Component(name='control', strict=True).add_check(guild_c).set_hooks(music_h)
)


logger = logging.getLogger(f"{'control':<{LOG_PAD}}")
logger.setLevel(logging.DEBUG)


from .queue import repeat_abs, shuffle_impl
from .playback import skip_abs, previous_abs, play_pause_impl


skip_impl = check(
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE__SPEAK__NP_YOURS,
)(skip_abs)
repeat_impl = check(Checks.QUEUE | Checks.CONN | Checks.IN_VC_ALONE)(repeat_abs)
previous_impl = check(Checks.CONN | Checks.QUEUE | Checks.ALONE__SPEAK__CAN_SEEK_ANY)(
    previous_abs
)


# ~


@control.with_listener(hk.InteractionCreateEvent)
async def on_interaction_create(
    event: hk.InteractionCreateEvent, lvc: al.Injected[lv.Lavalink]
):
    if not isinstance(inter := event.interaction, hk.ComponentInteraction):
        return

    assert inter.guild_id
    try:
        d = await get_data(inter.guild_id, lvc)
        if inter.channel_id != d.out_channel_id:
            return
    except NotConnected:
        return

    btt = inter.custom_id
    if btt == 'lyra_skip':
        await skip_impl(inter, lvc=lvc)
    elif btt == 'lyra_previous':
        await previous_impl(inter, lvc=lvc)
    elif btt == 'lyra_playpause':
        await play_pause_impl(inter, lvc=lvc)
    elif btt == 'lyra_shuffle':
        await shuffle_impl(inter, lvc=lvc)
    elif btt == 'lyra_repeat':
        await repeat_impl(inter, None, lvc=lvc)
    else:
        return


# -


loader = control.make_loader()
