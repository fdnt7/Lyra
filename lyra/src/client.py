import os
import yaml

# import yuyo
# import miru
import typing as t
import logging
import pathlib as pl
import hikari as hk
import alluka as al
import tanjun as tj
import lavasnek_rs as lv

from .lib import (
    repeat_emojis,
    EventHandler,
    EmojiRefs,
    GuildConfig,
    cfg_ref,
    base_h,
    restricts_c,
    update_cfg,
    inj_glob,
)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


fn = next(inj_glob('./config.yml'))

with open(fn.resolve(), 'r') as f:
    _y = yaml.load(f, yaml.Loader)

    PREFIX: list[str] = _y['prefixes']

    _dev: bool = _y['dev_mode']
    TOKEN: str = os.environ['LYRA_DEV_TOKEN' if _dev else 'LYRA_TOKEN']

    decl_glob_cmds: list[int] | t.Literal[True] = _y['guilds'] if _dev else True


client = (
    tj.Client.from_gateway_bot(
        bot := hk.GatewayBot(token=TOKEN),
        declare_global_commands=(decl_glob_cmds),
        mention_prefix=True,
    )
    .add_prefix(PREFIX)
    .set_hooks(base_h)
    .add_check(restricts_c)
    .load_modules(*('src.modules.' + p.stem for p in pl.Path('.').glob('./src/modules/*.py')))
)

activity = hk.Activity(name='/play', type=hk.ActivityType.LISTENING)


lavalink_client: lv.Lavalink
emoji_refs = EmojiRefs({})

cfg_fetched: t.Any = cfg_ref.get()
guild_config = GuildConfig(cfg_fetched)
logger.info("Loaded guild_configs")


@client.with_prefix_getter
async def prefix_getter(
    ctx: tj.abc.MessageContext, cfg: al.Injected[GuildConfig]
) -> t.Iterable[str]:
    prefixes: list[str] = (
        cfg.setdefault(str(ctx.guild_id), {}).setdefault('prefixes', [])
        if ctx.guild_id
        else []
    )
    return prefixes


EMOJIS_ACCESS = 777069316247126036


@client.with_listener(hk.StartedEvent)
async def on_started(
    _: hk.StartedEvent,
    client_: al.Injected[tj.Client],
):
    emojis = await client_.rest.fetch_guild_emojis(EMOJIS_ACCESS)

    emoji_refs.update({e.name: e for e in emojis})

    client_.set_type_dependency(GuildConfig, guild_config).set_type_dependency(
        EmojiRefs, emoji_refs
    )

    repeat_emojis.extend(emoji_refs[f'repeat{n}_b'] for n in range(3))


@client.with_listener(hk.ShardReadyEvent)
async def on_shard_ready(
    event: hk.ShardReadyEvent,
    client_: al.Injected[tj.Client],
) -> None:
    """Event that triggers when the hikari gateway is ready."""

    host = (
        os.environ['LAVALINK_HOST']
        if os.environ.get('IN_DOCKER', False)
        else '127.0.0.1'
    )

    builder = (
        lv.LavalinkBuilder(event.my_user.id, TOKEN)
        .set_host(host)
        .set_password(os.environ['LAVALINK_PASSWORD'])
        .set_port(int(os.environ['LAVALINK_PORT']))
        .set_start_gateway(False)
    )

    lvc = await builder.build(EventHandler())

    global lavalink_client
    lavalink_client = lvc
    client_.set_type_dependency(lv.Lavalink, lvc)

    # app_id = 0
    # guild_ids = []
    # _L = len(guild_ids)
    # for i, g in enumerate(guild_ids, 1):
    #     # print(await bot.rest.fetch_guild(g))
    #     cmds = await bot.rest.fetch_application_commands(698222394548027492, g)
    #     L = len(cmds)
    #     for j, cmd in enumerate(cmds, 1):
    #         await cmd.delete()
    #         print(f"#{i}/{_L} {j}/{L} {g}", cmd)


@client.with_listener(hk.VoiceStateUpdateEvent)
async def on_voice_state_update(
    event: hk.VoiceStateUpdateEvent,
    lvc: al.Injected[lv.Lavalink],
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
    lvc: al.Injected[lv.Lavalink],
) -> None:
    """Passes voice server updates to lavalink."""
    if event.endpoint is not None:
        await lvc.raw_handle_event_voice_server_update(
            event.guild_id,
            event.endpoint,
            event.token,
        )


@client.with_listener(hk.StoppingEvent)
async def on_stopping(_: hk.StoppingEvent, cfg: al.Injected[GuildConfig]) -> None:
    update_cfg(cfg)
