# pyright: reportUnusedImport=false
from .errors import (
    Argument,
    RequestedToSpeak,
    ChannelMoved,
    BaseLyraError,
    CommandCancelledError,
    ErrorNotRecognizedError,
    InternalError,
    NotInVoiceError,
    PlaybackChangeRefused,
    UnauthorizedError,
    OthersListeningError,
    OthersInVoiceError,
    AlreadyConnectedError,
    NotConnectedError,
    QueueEmptyError,
    NotYetSpeakerError,
    NotPlayingError,
    TrackPausedError,
    QueryEmptyError,
    TrackStoppedError,
    NoPlayableTracksError,
    NotDeveloperError,
    VotingTimeoutError,
    ForbiddenError,
    RestrictedError,
    LyricsNotFoundError,
    IllegalArgumentError,
    InvalidArgumentError,
)
from .expects import CheckErrorExpects, BindErrorExpects
