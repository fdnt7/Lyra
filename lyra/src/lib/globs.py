import sys

import tanjun as tj

from src.lib.dataimpl import LyraDBClientType


# pyright: reportGeneralTypeIssues=false
this = sys.modules[__name__]
this.client = None
this.mongo_client = None


def init_client(client: tj.Client):
    if this.client is None:
        this.client = client
        return client
    raise RuntimeError(f"Client already initialized: {this.client}")


def init_mongo_client(client: LyraDBClientType):
    if this.mongo_client is None:
        this.mongo_client = client
        return client
    raise RuntimeError(f"MongoDB client already initialized: {this.mongo_client}")
