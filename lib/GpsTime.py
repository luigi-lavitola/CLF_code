"""
UNIX time <-> GPS time (seconds since 1980-01-06 00:00:00 UTC, leap seconds included).

GPS = UNIX - GPS_EPOCH_UNIX + (GPS - UTC offset at that time)

The offset changes only when IERS adds a leap second (announced ~6 months in advance
in Bulletin C): add a line to LEAP_SECONDS when that happens.
"""

import bisect

GPS_EPOCH_UNIX = 315_964_800        # 1980-01-06 00:00:00 UTC

# (UNIX time from which the offset applies, GPS - UTC in seconds)
LEAP_SECONDS = [
    (362_793_600, 1),       # 1981-07-01
    (394_329_600, 2),       # 1982-07-01
    (425_865_600, 3),       # 1983-07-01
    (489_024_000, 4),       # 1985-07-01
    (567_993_600, 5),       # 1988-01-01
    (631_152_000, 6),       # 1990-01-01
    (662_688_000, 7),       # 1991-01-01
    (709_948_800, 8),       # 1992-07-01
    (741_484_800, 9),       # 1993-07-01
    (773_020_800, 10),      # 1994-07-01
    (820_454_400, 11),      # 1996-01-01
    (867_715_200, 12),      # 1997-07-01
    (915_148_800, 13),      # 1999-01-01
    (1_136_073_600, 14),    # 2006-01-01
    (1_230_768_000, 15),    # 2009-01-01
    (1_341_100_800, 16),    # 2012-07-01
    (1_435_708_800, 17),    # 2015-07-01
    (1_483_228_800, 18),    # 2017-01-01
]
_STARTS = [s for s, _ in LEAP_SECONDS]


def gps_utc_offset(unix_seconds):
    """GPS - UTC (leap seconds since 1980) valid at a UNIX time."""
    i = bisect.bisect_right(_STARTS, unix_seconds)
    return LEAP_SECONDS[i - 1][1] if i else 0


def unix_to_gps(unix_seconds):
    return unix_seconds - GPS_EPOCH_UNIX + gps_utc_offset(unix_seconds)


def gps_to_unix(gps_seconds):
    unix = gps_seconds + GPS_EPOCH_UNIX
    # the offset is a function of UNIX time: iterate once more near a leap second
    for _ in range(2):
        unix = gps_seconds + GPS_EPOCH_UNIX - gps_utc_offset(unix)
    return unix
