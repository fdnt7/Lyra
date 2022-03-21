import os
import re
import logging
import firebase_admin as fb  # type: ignore

from firebase_admin import db  # type: ignore
from firebase_admin import credentials  # type: ignore
from .utils import GuildConfig
from .extras import inj_glob

logger = logging.getLogger(__name__)

FIREBASE_KEYS = re.compile(r'^.*-db-.*-adminsdk-.*.json$')
keys = next(filter(lambda f: FIREBASE_KEYS.match(f.name), inj_glob('./*.json')))

cert = credentials.Certificate(keys.resolve())

app = fb.initialize_app(  # type: ignore
    cert,
    {'databaseURL': os.environ['FIREBASE_URL']},
)

cfg_ref = db.reference('guild_configs')  # type: ignore


def update_cfg(cfg: GuildConfig):
    if not os.environ.get('IN_DOCKER', False):
        return
    cfg_ref.set(dict(cfg))  # type: ignore
    logger.info("Saved to guild_configs")
