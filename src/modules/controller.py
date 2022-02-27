from src.lib.music import *
from src.lib.checks import check, Checks


control = (
    tj.Component(name='control', strict=True).add_check(guild_c).set_hooks(music_h)
)


@control.with_listener(hk.InteractionCreateEvent)
async def on_interaction_create(
    event: hk.InteractionCreateEvent, lvc: lv.Lavalink = tj.inject(type=lv.Lavalink)
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
        await check(
            Checks.PLAYING | Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CURR_T_YOURS,
        )(skip_impl)(inter, lvc=lvc)
    elif btt == 'lyra_previous':
        await check(Checks.CONN | Checks.QUEUE | Checks.ALONE_OR_CAN_SEEK_QUEUE)(
            previous_impl
        )(inter, lvc=lvc)
    elif btt == 'lyra_playpause':
        await play_pause_impl(inter, lvc=lvc)
    elif btt == 'lyra_shuffle':
        await shuffle_impl(inter, lvc=lvc)
    elif btt == 'lyra_repeat':
        await repeat_impl(inter, None, lvc=lvc)
    else:
        return


# -


loader = control.load_from_scope().make_loader()
