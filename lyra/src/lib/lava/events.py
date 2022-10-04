import abc

import attr as a
import hikari as hk

# pyright: reportIncompatibleMethodOverride=false


@a.define
class BaseLyraEvent(hk.Event, abc.ABC):
    app: hk.RESTAware


@a.frozen
class InternalConnectionChangeEvent(BaseLyraEvent):
    pass


@a.frozen
class ConnectionCommandsInvokedEvent(InternalConnectionChangeEvent):
    pass


@a.frozen
class AutomaticConnectionChangeEvent(InternalConnectionChangeEvent):
    pass


@a.frozen
class TrackStoppedEvent(BaseLyraEvent):
    pass
