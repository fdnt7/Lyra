import os
import typing as t
import logging

import pymongo.collection as mg_co
import pymongo.mongo_client as mg_cl

import src.lib.globs as globs

from .extras import lgfmt

# import firebase_admin as fb

# from firebase_admin import db
# from firebase_admin import credentials
# from .extras import inj_glob

logger = logging.getLogger(lgfmt(__name__))

# FIREBASE_KEYS = re.compile(r'^.*-db-.*-adminsdk-.*.json$')
# keys = next(filter(lambda f: FIREBASE_KEYS.match(f.name), inj_glob('./*.json')))

# cert = credentials.Certificate(keys.resolve())

# app = fb.initialize_app(
#     cert,
#     {'databaseURL': os.environ['FIREBASE_URL']},
# )

# cfg_ref = db.reference('guild_configs')


# class GuildConfig(dict[str, dict[str, t.Any]]):
#     def __init__(self, *args: t.Any, **kwargs: t.Any):
#         logger.info("Loaded guild_configs")
#         super().__init__(*args, **kwargs)


# def update_cfg(cfg: GuildConfig):
#     if not os.environ.get('IN_DOCKER', False):
#         return
#     cfg_ref.set(dict(cfg))
#     logger.info("Saved to guild_configs")


conn_str = os.environ['MONGODB_CONN_STR']
pwd = os.environ['MONGODB_PWD']

LyraDBDocumentType = dict[str, t.Any]
LyraDBClientType = mg_cl.MongoClient[LyraDBDocumentType]
LyraDBCollectionType = mg_co.Collection[LyraDBDocumentType]

_client: LyraDBClientType = mg_cl.MongoClient(conn_str % pwd)


def init_mongo_client():
    logger.info("Connected to MongoDB Database")
    return globs.init_mongo_client(_client)
