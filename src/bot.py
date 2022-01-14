import os

import hikari as hk
import tanjun as tj
import lavasnek_rs as lv
import pathlib as pl

from src import EventHandler, hooks
from src.lib.music import access_equalizer, NotConnected


PREFIX = ','
# TOKEN = os.environ['SYMPNOIA_TOKEN']
TOKEN = os.environ['SYMPNOIA_DEV_TOKEN']

guild_ids = (
    777069316247126036,  # Dev
    # 733408768230162538,  # Cnrcord
    # 703617620540391496,  # Jakkapoolu
    # 689006349002342401,  # SMTE
    # 674259790259814440,  # Hayacord
)


client = (
    tj.Client.from_gateway_bot(
        bot := hk.GatewayBot(token=TOKEN),
        declare_global_commands=(
            guild_ids
            # True
        ),
        mention_prefix=True,
    )
    .add_prefix(PREFIX)
    .set_hooks(hooks)
    .load_modules(*(p for p in pl.Path('.').glob('./src/modules/*.py')))
)


@client.with_listener(hk.ShardReadyEvent)
async def on_shard_ready(
    event: hk.ShardReadyEvent,
    client_: tj.Client = tj.injected(type=tj.Client),
) -> None:
    """Event that triggers when the hikari gateway is ready."""
    builder = (
        lv.LavalinkBuilder(event.my_user.id, TOKEN)
        .set_host(os.environ['LAVALINK_HOST'])
        .set_password(os.environ['LAVALINK_PASSWORD'])
        .set_port(int(os.environ['LAVALINK_PORT']))
        .set_start_gateway(False)
    )

    client_.set_type_dependency(
        lv.Lavalink, await builder.build(EventHandler())
    ).set_type_dependency(hk.GatewayBot, bot)

    assert client_.shards is not None

    # for i,g in enumerate(guild_ids, 1):
    #     # print(await bot.rest.fetch_guild(g))
    #     _L = len(guild_ids)
    #     cmds = await bot.rest.fetch_application_commands(698222394548027492, g)
    #     L = len(cmds)
    #     for j,cmd in enumerate(cmds, 1):
    #         await cmd.delete()
    #         print(f"{i}/{_L} {j}/{L}", cmd)


@client.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Passes voice state updates to lavalink."""

    new = event.state
    # old = event.old_state
    try:
        async with access_equalizer(event.guild_id, lvc) as eq:
            eq.is_muted = new.is_guild_muted
    except NotConnected:
        pass

    await lvc.raw_handle_event_voice_state_update(
        new.guild_id,
        new.user_id,
        new.session_id,
        new.channel_id,
    )


@client.with_listener(hk.VoiceServerUpdateEvent)
async def on_voice_server_update(
    event: hk.VoiceServerUpdateEvent,
    lvc: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Passes voice server updates to lavalink."""
    if event.endpoint is not None:
        await lvc.raw_handle_event_voice_server_update(
            event.guild_id,
            event.endpoint,
            event.token,
        )
