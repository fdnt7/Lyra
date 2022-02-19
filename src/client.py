import os
import json
import yaml

# import yuyo
# import miru
import typing as t
import logging
import hikari as hk
import tanjun as tj
import lavasnek_rs as lv
import pathlib as pl

from src.lib import *


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


with open('config.yml', 'r') as f:
    _y = yaml.load(f, yaml.Loader)

    PREFIX: list[str] = _y['prefixes']

    _dev: bool = _y['dev_mode']
    TOKEN: str = os.environ['LYRA_DEV_TOKEN' if _dev else 'LYRA_TOKEN']

    guild_ids: list[int] = _y['dev_guilds'] if _dev else _y['rel_guilds']


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
# miru.load(bot)


# yuyo_client = yuyo.ComponentClient.from_gateway_bot(bot)
lavalink_client: lv.Lavalink


with open('guild_settings.json', 'r') as f:
    guild_config: GuildConfig = json.load(f)
    logger.info("Loaded guild_settings.json")


(
    client.set_type_dependency(GuildConfig, guild_config)
    # .set_type_dependency(yuyo.ComponentClient, yuyo_client)
)


@client.with_prefix_getter
async def prefix_getter(ctx: tj.abc.MessageContext) -> t.Iterable[str]:
    return (
        guild_config.setdefault(str(ctx.guild_id), {}).setdefault('prefixes', [])
        if ctx.guild_id
        else []
    )


@client.with_listener(hk.ShardReadyEvent)
async def on_shard_ready(
    event: hk.ShardReadyEvent,
    client_: tj.Client = tj.inject(type=tj.Client),
) -> None:
    """Event that triggers when the hikari gateway is ready."""
    builder = (
        lv.LavalinkBuilder(event.my_user.id, TOKEN)
        .set_host(os.environ['LAVALINK_HOST'])
        .set_password(os.environ['LAVALINK_PASSWORD'])
        .set_port(int(os.environ['LAVALINK_PORT']))
        .set_start_gateway(False)
    )

    lvc = await builder.build(EventHandler())

    global lavalink_client
    lavalink_client = lvc
    client_.set_type_dependency(lv.Lavalink, lvc)

    # for i,g in enumerate(guild_ids, 1):
    #     # print(await bot.rest.fetch_guild(g))
    #     _L = len(guild_ids)
    #     cmds = await bot.rest.fetch_application_commands(901543206947262475)
    #     L = len(cmds)
    #     for j,cmd in enumerate(cmds, 1):
    #         await cmd.delete()
    #         print(f"{i}/{_L} {j}/{L}", cmd)


@client.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Passes voice state updates to lavalink."""

    new = event.state
    # old = event.old_state

    lvc.raw_handle_event_voice_state_update(
        new.guild_id,
        new.user_id,
        new.session_id,
        new.channel_id,
    )


@client.with_listener(hk.VoiceServerUpdateEvent)
async def on_voice_server_update(
    event: hk.VoiceServerUpdateEvent,
    lvc: lv.Lavalink = tj.inject(type=lv.Lavalink),
) -> None:
    """Passes voice server updates to lavalink."""
    if event.endpoint is not None:
        await lvc.raw_handle_event_voice_server_update(
            event.guild_id,
            event.endpoint,
            event.token,
        )


@client.with_listener(hk.StoppingEvent)
async def on_stopping(_: hk.StoppingEvent) -> None:
    with open('guild_settings.json', 'w') as f:
        json.dump(guild_config, f, indent=4)
        logger.info("Saved to guild_settings.json")
