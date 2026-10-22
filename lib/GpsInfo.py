"""
Receiver and time-reference information from the gpsd reports (JSON protocol):

  TPV  fix: time, lat, lon, altHAE/alt, leapseconds (newer gpsd)
  SKY  satellites (PRN, el, az, ss = SNR, used), nSat/uSat (newer gpsd), hdop, tdop
  PPS  real_sec/real_nsec (GPS second of the PPS edge) and clock_sec/clock_nsec (host
       clock at that edge): only when gpsd has a PPS source (WATCH_PPS)

The last report of each class is kept; values older than STALE_S are not used.
Fields missing in a given gpsd version / receiver give NaN.
"""

import math
import time
from datetime import datetime, timezone

from lib.GpsTime import gps_utc_offset

STALE_S = 10

# host clock - GPS beyond these values: the FPGA time alignment (TimeSync, which uses the
# host clock) may write the wrong second. TPV time includes the reporting latency of the
# receiver, so it is a coarser measurement than PPS.
CLOCK_OFFSET_WARN_S = {"PPS": 0.1, "TPV": 0.5}

FIELDS = ("gps_sats_used", "gps_sats_visible", "gps_snr_mean", "gps_hdop", "gps_tdop",
          "gps_lat", "gps_lon", "gps_alt", "gps_clock_offset", "gps_leapseconds")

NAN = float("nan")


def _get(obj, key, default=None):
    """Field of a report: plain dict or gps.dictwrapper (both support get())."""
    try:
        value = obj.get(key, default)
    except AttributeError:
        return default
    return default if value is None else value


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return NAN


def _iso_to_unix(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


class GpsStatus:

    def __init__(self):
        self.reports = {}               # class -> (host time when received, report)

    def update(self, report, host_time=None):
        cls = _get(report, "class")
        if cls:
            self.reports[cls] = (time.time() if host_time is None else host_time, report)

    def _last(self, cls, now):
        t, report = self.reports.get(cls, (None, None))
        return report if t is not None and now - t <= STALE_S else None

    def clock_offset(self, now):
        """(host clock - GPS in s, source 'PPS'/'TPV'), (NaN, None) if not available."""
        pps = self._last("PPS", now)
        if pps is not None and _get(pps, "real_sec") is not None:
            # seconds and nanoseconds subtracted separately: summing them first (~1.8e9 s)
            # would lose the ns resolution in floating point
            d_sec = _num(_get(pps, "clock_sec")) - _num(_get(pps, "real_sec"))
            d_nsec = _num(_get(pps, "clock_nsec", 0)) - _num(_get(pps, "real_nsec", 0))
            return d_sec + d_nsec * 1e-9, "PPS"
        t, tpv = self.reports.get("TPV", (None, None))
        if tpv is not None and now - t <= STALE_S:
            fix_time = _iso_to_unix(_get(tpv, "time"))
            if fix_time is not None:
                return t - fix_time, "TPV"
        return NAN, None

    def values(self, now):
        sky = self._last("SKY", now)
        tpv = self._last("TPV", now)
        v = dict.fromkeys(FIELDS, NAN)
        if sky is not None:
            sats = _get(sky, "satellites", []) or []
            used = [s for s in sats if _get(s, "used")]
            v["gps_sats_used"] = _num(_get(sky, "uSat", len(used)))
            v["gps_sats_visible"] = _num(_get(sky, "nSat", len(sats)))
            snr = [_num(_get(s, "ss")) for s in used]
            snr = [x for x in snr if not math.isnan(x)]
            v["gps_snr_mean"] = sum(snr) / len(snr) if snr else NAN
            v["gps_hdop"] = _num(_get(sky, "hdop"))
            v["gps_tdop"] = _num(_get(sky, "tdop"))
        if tpv is not None:
            v["gps_lat"] = _num(_get(tpv, "lat"))
            v["gps_lon"] = _num(_get(tpv, "lon"))
            v["gps_alt"] = _num(_get(tpv, "altHAE", _get(tpv, "alt")))
            v["gps_leapseconds"] = _num(_get(tpv, "leapseconds"))
        v["gps_clock_offset"], _ = self.clock_offset(now)
        return v

    def warnings(self, now):
        """{key: message} for conditions that make the timestamps unreliable."""
        out = {}
        off, source = self.clock_offset(now)
        if source is not None and abs(off) > CLOCK_OFFSET_WARN_S[source]:
            out["clock"] = (f"host clock - GPS = {off:+.3f} s ({source}): FPGA time alignment may "
                            "write the wrong second, check NTP/chrony")
        tpv = self._last("TPV", now)
        leap = _get(tpv, "leapseconds") if tpv is not None else None
        if leap is not None:
            table = gps_utc_offset(int(now))
            if int(leap) != table:
                out["leap"] = (f"GPS reports {int(leap)} leap seconds, lib/GpsTime.py has {table}: "
                               "add the new leap second to LEAP_SECONDS")
        return out
