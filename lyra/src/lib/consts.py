"""Feel free to change these"""
import typing as t


LOG_PAD: t.Final = 16
"""Left aligned padding for each lib's logger name"""
TIMEOUT: t.Final = 60
"""Base timeout time for buttons, drop-downs and command's wait for responses in seconds"""
Q_CHUNK: t.Final = 15
"""Amount of tracks in the queue to be displayed per page in the `/queue` command"""
RETRIES: t.Final = 3
"""Amount of tries to retry when some over-the-web operations failed"""
STOP_REFRESH: t.Final = 0.15
"""How many seconds to wait before checking the next time whether the track is confirmed to be stopped"""
ADD_TRACKS_WRAP_LIM: t.Final = 3
"""How many tracks to be displayed in `/play`'s output before the text got summarized to "Added <i> tracks...\""""

genius_icon: t.Final = (
    'https://images.genius.com/2f65c7544798653b46b7a1f132ce8768.512x512x1.png'
)
lyricfind_icon: t.Final = 'https://scontent.furt2-1.fna.fbcdn.net/v/t39.30808-6/271855185_10160258822139586_9124911043791941795_n.jpg?_nc_cat=109&ccb=1-5&_nc_sid=09cbfe&_nc_eui2=AeG7FaxAvBMoYaNVXaD6lZc3ieYAOyp56QqJ5gA7KnnpChOz458NfnNsOXzFYQMKsDqZO1BNOdAeVo65cTPGZZtR&_nc_ohc=pLUiZF5kRRcAX_tVA5y&_nc_ht=scontent.furt2-1.fna&oh=00_AT8B2CtyltZqKo3GZRHSEExIXh5asH9l5N6okOLazDe7iw&oe=62056385'

__developers__: t.Final = frozenset((548850193202675713, 626062879531204618))
"""Who the `debug` commands can be used"""
__version__: t.Final = '2.4.1a1'
