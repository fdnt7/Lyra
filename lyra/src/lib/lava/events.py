import abc

import attr as a
import hikari as hk

# pyright: reportIncompatibleMethodOverride=false


@a.define
class BaseLyraEvent(hk.Event, abc.ABC):
    app: hk.RESTAware


@a.frozen
class ConnectionCommandsInvokedEvent(BaseLyraEvent):
    pass


@a.frozen
class TrackStoppedEvent(BaseLyraEvent):
    pass
