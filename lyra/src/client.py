import os
import typing as t
import logging
import pathlib as pl

import yaml
import hikari as hk
import alluka as al
import tanjun as tj
import lavasnek_rs as lv

import src.lib.globs as globs

from .lib import (
    EventHandler,
    LyraConfig,
    LyraDBClientType,
    LyraDBCollectionType,
    repeat_emojis,
    EmojiRefs,
    base_h,
    __init_mongo_client__,
    restricts_c,
    inj_glob,
    lgfmt,
)

# pyright: reportUnknownMemberType=false


logger = logging.getLogger(lgfmt(__name__))
logger.setLevel(logging.DEBUG)


fn = next(inj_glob('./config.yml'))

with open(fn.resolve(), 'r') as f:
    _d = yaml.load(f, yaml.Loader)

    lyra_config = LyraConfig(
        prefixes=_d['prefixes'],
        is_dev_mode=(_dev := _d['dev_mode']),
        token=os.environ['LYRA_DEV_TOKEN' if _dev else 'LYRA_TOKEN'],
        decl_glob_cmds=_d['guilds'] if _dev else True,
        emoji_guild=_d['emoji_guild'],
    )

_client = globs.__init_client__(
    tj.Client.from_gateway_bot(
        bot := hk.GatewayBot(token=lyra_config.token),
        declare_global_commands=(lyra_config.decl_glob_cmds),
        mention_prefix=True,
    )
    .add_prefix(lyra_config.prefixes)
    .set_hooks(base_h)
    .add_check(restricts_c)
    .load_modules(
        *('src.modules.' + p.stem for p in pl.Path('.').glob('./src/modules/*.py'))
    )
    .set_dms_enabled_for_app_cmds(False)
    .set_type_dependency(LyraConfig, lyra_config)
)

activity = hk.Activity(
    name="%s" % '/play',
    type=hk.ActivityType.LISTENING,
)

emoji_refs = EmojiRefs({})


@_client.with_prefix_getter
async def prefix_getter(
    ctx: tj.abc.MessageContext,
    cfg: al.Injected[LyraDBCollectionType],
) -> t.Iterable[str]:
    g_id = str(ctx.guild_id)
    flt = {'id': g_id}

    if _g_cfg := cfg.find_one(flt):
        g_cfg = _g_cfg
    else:
        cfg.insert_one(flt)
        g_cfg: dict[str, t.Any] = flt.copy()

    prefixes: list[str] = g_cfg.setdefault('prefixes', []) if ctx.guild_id else []
    return prefixes


@_client.with_listener()
async def on_started(
    _: hk.StartedEvent,
    client: al.Injected[tj.Client],
):
    emojis = await client.rest.fetch_guild_emojis(lyra_config.emoji_guild)
    emoji_refs.update({e.name: e for e in emojis})
    logger.info("Fetched emojis from Lýra's Emoji Server")

    mongo_client = __init_mongo_client__()

    prefs_db = mongo_client.get_database('prefs')
    guilds_co = prefs_db.get_collection('guilds')

    (
        client.set_type_dependency(LyraDBClientType, mongo_client)
        .set_type_dependency(LyraDBCollectionType, guilds_co)
        .set_type_dependency(EmojiRefs, emoji_refs)
    )

    repeat_emojis.extend(emoji_refs[f'repeat{n}_b'] for n in range(3))


@_client.with_listener()
async def on_shard_ready(
    event: hk.ShardReadyEvent,
    client: al.Injected[tj.Client],
) -> None:
    """Event that triggers when the hikari gateway is ready."""

    host = (
        os.environ['LAVALINK_HOST']
        if os.environ.get('IN_DOCKER', False)
        else '127.0.0.1'
    )

    builder = (
        lv.LavalinkBuilder(event.my_user.id, lyra_config.token)
        .set_host(host)
        .set_password(os.environ['LAVALINK_PWD'])
        .set_port(int(os.environ['LAVALINK_PORT']))
        .set_start_gateway(False)
    )

    lvc = await builder.build(EventHandler())

    client.set_type_dependency(lv.Lavalink, lvc)


@_client.with_listener()
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


@_client.with_listener()
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
