import os
import re
import pathlib as pl
import firebase_admin as fb

from firebase_admin import db
from firebase_admin import credentials
from .utils import inj_glob

FIREBASE_KEYS = re.compile(r'^.*-db-.*-adminsdk-.*.json$')
keys = next(filter(lambda f: FIREBASE_KEYS.match(f.name), inj_glob('./*.json')))

cert = credentials.Certificate(keys.resolve())

app = fb.initialize_app(
    cert,
    {'databaseURL': os.environ['FIREBASE_URL']},
)

cfg_ref = db.reference('guild_configs')
