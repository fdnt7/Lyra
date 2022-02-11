import os
import json
import yaml
import typing as t
import logging
import asyncio
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


with open('guild_settings.json', 'r') as f:
    guild_settings: GuildSettings = json.load(f)
    logger.info("Loaded guild_settings.json")


@client.with_prefix_getter
async def prefix_getter(ctx: tj.abc.MessageContext) -> t.Iterable[str]:
    return (
        guild_settings.setdefault(str(ctx.guild_id), {}).setdefault('prefixes', [])
        if ctx.guild_id
        else []
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

    (
        client_.set_type_dependency(lv.Lavalink, await builder.build(EventHandler()))
        .set_type_dependency(hk.GatewayBot, bot)
        .set_type_dependency(GuildSettings, guild_settings)
    )

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

    async def _conn():
        return lvc.get_guild_gateway_connection_info(event.guild_id)

    new = event.state
    old = event.old_state

    lvc.raw_handle_event_voice_state_update(
        new.guild_id,
        new.user_id,
        new.session_id,
        new.channel_id,
    )

    if not (conn := await _conn()):
        return

    try:
        async with access_equalizer(event.guild_id, lvc) as eq:
            eq.is_muted = new.is_guild_muted
    except NotConnected:
        return

    assert isinstance(conn, dict)

    _in_voice = lambda: set(
        filter(
            lambda v: not v.member.is_bot,
            client.cache.get_voice_states_view_for_channel(  # type: ignore
                event.guild_id, conn['channel_id']
            ).values(),
        )
    )

    ch = (d := await get_data(event.guild_id, lvc)).out_channel_id
    assert ch

    q = d.queue

    async def on_everyone_leaves_vc():
        logger.debug(
            f"In guild {event.guild_id} started channel {conn['channel_id']} timeout inactivity"
        )
        for _ in range(10):
            if len(_in_voice()) >= 1 or not (await _conn()):
                logger.debug(
                    f"In guild {event.guild_id} stopped channel {conn['channel_id']} timeout inactivity"
                )
                return False
            await asyncio.sleep(60)

        __conn = await _conn()
        assert isinstance(__conn, dict)

        await cleanups__(event.guild_id, client.shards, lvc)
        logger.info(
            f"In guild {event.guild_id} left   channel {(_vc := __conn['channel_id'])} due to inactivity"
        )
        await client.rest.create_message(
            ch, f"🍃📎 ~~<#{_vc}>~~ `(Left due to inactivity)`"
        )

        return True

    from src.lib.music import set_pause__

    in_voice = _in_voice()
    vc: int = conn['channel_id']
    bot_u = bot.get_me()
    assert bot_u
    # if new.channel_id == vc and len(in_voice) == 1 and new.user_id != bot_u.id:
    #     # Someone rejoined
    #     try:
    #         await set_pause__(event.guild_id, lvc, pause=False)
    #         await client.rest.create_message(ch, f"✨⏸️ Resumed")
    #     except NotConnected:
    #         pass

    if (new.channel_id != vc) and not in_voice:
        if old and old.channel_id == vc:
            # Everyone left
            await set_pause__(event.guild_id, lvc, pause=True)
            await client.rest.create_message(ch, f"✨▶️ Paused as no one is listening")

            await asyncio.wait(
                [loop.create_task(on_everyone_leaves_vc())],
                return_when=asyncio.FIRST_COMPLETED,
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


@client.with_listener(hk.StoppingEvent)
async def on_stopping(event: hk.StoppingEvent) -> None:
    # from src.lib.utils import loop

    # loop.run_forever()
    # loop.close()

    with open('guild_settings.json', 'w') as f:
        json.dump(guild_settings, f, indent=4)
        logger.info("Saved to guild_settings.json")
