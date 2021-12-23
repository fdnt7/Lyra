from src.lib.music import *


tuning = tj.Component(checks=(guild_c,), hooks=music_h)


# -


@tj.as_loader
def load_component(client: tj.abc.Client) -> None:
    client.add_component(tuning.copy())
