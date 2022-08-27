import hikari as hk
import alluka as al
import lavasnek_rs as lv

from ..lib.musicutils import __init_component__
from ..lib.errors import NotConnected
from ..lib.extras import void
from ..lib.flags import (
    ALONE__SPEAK__CAN_SEEK_ANY,
    ALONE__SPEAK__NP_YOURS,
    IN_VC_ALONE,
)
from ..lib.compose import (
    Checks,
    with_cb_check,
)
from ..lib.lavautils import get_data


control = __init_component__(__name__)


from .queue import repeat_abs, shuffle_abs
from .playback import skip_abs, previous_abs, play_pause_abs

play_pause_impl = with_cb_check(
    Checks.PLAYING
    | Checks.ADVANCE
    | Checks.CONN
    | Checks.QUEUE
    | ALONE__SPEAK__NP_YOURS
)(void(play_pause_abs))
skip_impl = with_cb_check(
    Checks.PLAYING | Checks.CONN | Checks.QUEUE | ALONE__SPEAK__NP_YOURS,
)(skip_abs)
previous_impl = with_cb_check(Checks.CONN | Checks.QUEUE | ALONE__SPEAK__CAN_SEEK_ANY)(
    previous_abs
)
repeat_impl = with_cb_check(Checks.QUEUE | Checks.CONN | IN_VC_ALONE)(repeat_abs)
shuffle_impl = with_cb_check(Checks.QUEUE | Checks.CONN | IN_VC_ALONE)(shuffle_abs)


# ~


@control.with_listener()
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
        await skip_impl(inter, lvc)
    elif btt == 'lyra_previous':
        await previous_impl(inter, lvc)
    elif btt == 'lyra_playpause':
        await play_pause_impl(inter, lvc)
    elif btt == 'lyra_shuffle':
        await shuffle_impl(inter, lvc)
    elif btt == 'lyra_repeat':
        await repeat_impl(inter, None, lvc)
    else:
        return


# -


loader = control.make_loader()
