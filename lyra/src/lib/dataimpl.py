import os
import re
import logging
import pathlib as pl
import firebase_admin as fb

from firebase_admin import db
from firebase_admin import credentials
from .utils import GuildConfig
from .extras import inj_glob

logger = logging.getLogger(__name__)

FIREBASE_KEYS = re.compile(r'^.*-db-.*-adminsdk-.*.json$')
keys = next(filter(lambda f: FIREBASE_KEYS.match(f.name), inj_glob('./*.json')))

cert = credentials.Certificate(keys.resolve())

app = fb.initialize_app(
    cert,
    {'databaseURL': os.environ['FIREBASE_URL']},
)

cfg_ref = db.reference('guild_configs')


def update_cfg(cfg: GuildConfig):
    cfg_ref.set(dict(cfg))
    logger.info("Saved to guild_configs")
