import os

import hikari as hk
import tanjun as tj
import lavasnek_rs as lv
import pathlib as pl

from src import EventHandler, hooks


PREFIX = ","
TOKEN = os.environ["SYMPNOIA_TOKEN"]


client = (
    tj.Client.from_gateway_bot(
        bot := hk.GatewayBot(token=TOKEN),
        declare_global_commands=(
            777069316247126036,
            703617620540391496,
            689006349002342401,
            674259790259814440,
        ),
        mention_prefix=True,
    )
    .add_prefix(PREFIX)
    .set_hooks(hooks)
    .load_modules(*(p for p in pl.Path(".").glob("./src/modules/*.py")))
)


@client.with_listener(hk.ShardReadyEvent)
async def on_shard_ready(
    event: hk.ShardReadyEvent,
    client_: tj.Client = tj.injected(type=tj.Client),
) -> None:
    """Event that triggers when the hikari gateway is ready."""
    builder = (
        lv.LavalinkBuilder(event.my_user.id, TOKEN)
        .set_host('0.0.0.0')
        .set_password(os.environ["LAVALINK_PASSWORD"])
        .set_port(int(os.environ["LAVALINK_PORT"]))
        .set_start_gateway(False)
    )
    print(os.environ["LAVALINK_HOST"], os.environ["LAVALINK_PASSWORD"], os.environ["LAVALINK_PORT"])

    client_.set_type_dependency(
        lv.Lavalink, await builder.build(EventHandler())
    ).set_type_dependency(hk.GatewayBot, bot)

    assert client_.shards is not None
    await client_.shards.update_presence(
        status=hk.Status.ONLINE, activity=hk.Activity(name=",pp")
    )


@client.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    lavalink: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Passes voice state updates to lavalink."""
    await lavalink.raw_handle_event_voice_state_update(
        event.state.guild_id,
        event.state.user_id,
        event.state.session_id,
        event.state.channel_id,
    )


@client.with_listener(hk.VoiceServerUpdateEvent)
async def on_voice_server_update(
    event: hk.VoiceServerUpdateEvent,
    lavalink: lv.Lavalink = tj.injected(type=lv.Lavalink),
) -> None:
    """Passes voice server updates to lavalink."""
    if event.endpoint is not None:
        await lavalink.raw_handle_event_voice_server_update(
            event.guild_id,
            event.endpoint,
            event.token,
        )
