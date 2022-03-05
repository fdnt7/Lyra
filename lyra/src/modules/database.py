from src.lib.utils import *

data = tj.Component(name='database', strict=True).add_check(guild_c)


@data.with_listener(hk.ShardResumedEvent)
async def on_shard_resumed(_: hk.ShardResumedEvent, cfg: al.Injected[GuildConfig]):
    from src.lib.dataimpl import update_cfg

    update_cfg(cfg)


# -


loader = data.make_loader()
