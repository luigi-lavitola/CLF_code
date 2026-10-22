"""GpsInfo: values from gpsd TPV / SKY / PPS reports, and timestamp-related warnings."""

import logging
import math
import types

import pytest

from lib.GpsInfo import GpsStatus, FIELDS
from lib.GpsTime import gps_utc_offset
from lib.HouseKeeping import HouseKeeping

NOW = 1_790_000_000.0       # 2026-09-21, GPS - UTC = 18 s

TPV = {"class": "TPV", "mode": 3, "time": "2026-09-21T14:13:19.800Z",
       "lat": -35.4955, "lon": -69.4497, "altHAE": 1420.3, "leapseconds": 18}
SKY = {"class": "SKY", "hdop": 0.8, "tdop": 1.1, "satellites": [
    {"PRN": 3, "el": 60, "az": 120, "ss": 44, "used": True},
    {"PRN": 7, "el": 35, "az": 200, "ss": 38, "used": True},
    {"PRN": 9, "el": 5, "az": 10, "ss": 12, "used": False}]}
PPS = {"class": "PPS", "real_sec": 1_790_000_000, "real_nsec": 0,
       "clock_sec": 1_790_000_000, "clock_nsec": 3_000_000}      # host 3 ms ahead


def status(*reports, at=NOW):
    s = GpsStatus()
    for r in reports:
        s.update(r, at)
    return s


def test_values_from_reports():
    v = status(TPV, SKY, PPS).values(NOW)
    assert v["gps_sats_used"] == 2 and v["gps_sats_visible"] == 3
    assert v["gps_snr_mean"] == 41.0                    # used satellites only
    assert v["gps_hdop"] == 0.8 and v["gps_tdop"] == 1.1
    assert (v["gps_lat"], v["gps_lon"], v["gps_alt"]) == (-35.4955, -69.4497, 1420.3)
    assert v["gps_leapseconds"] == 18
    assert v["gps_clock_offset"] == pytest.approx(0.003)


def test_newer_gpsd_counts_preferred():
    sky = dict(SKY, nSat=11, uSat=8)
    v = status(sky).values(NOW)
    assert v["gps_sats_used"] == 8 and v["gps_sats_visible"] == 11


def test_missing_fields_are_nan():
    v = status({"class": "TPV", "mode": 2}).values(NOW)  # old gpsd, no leapseconds/alt
    assert all(math.isnan(v[k]) for k in ("gps_leapseconds", "gps_alt", "gps_sats_used", "gps_clock_offset"))


def test_stale_reports_not_used():
    v = status(TPV, SKY, at=NOW - 60).values(NOW)
    assert all(math.isnan(v[k]) for k in FIELDS if k != "gps_fix_age")
    # the fix age uses the last TPV on purpose and is computed from its fix time
    # (2026-09-21T14:13:19.800Z = NOW - 0.2 s), not from when the report arrived
    assert v["gps_fix_age"] == pytest.approx(0.2, abs=0.05)


def test_clock_offset_from_tpv_without_pps():
    off, source = status(TPV, at=NOW).clock_offset(NOW)
    # received at NOW, fix time 2026-09-21T14:13:19.800Z = NOW - 0.2 s
    assert source == "TPV" and off == pytest.approx(0.2, abs=1e-6)


def test_no_warnings_when_good():
    assert status(TPV, SKY, PPS).warnings(NOW) == {}


def test_host_clock_warning():
    bad = dict(PPS, clock_sec=PPS["clock_sec"] + 1)      # host 1 s ahead of GPS
    w = status(TPV, bad).warnings(NOW)
    assert "clock" in w and "+1.003" in w["clock"]


def test_leap_second_table_warning():
    assert gps_utc_offset(int(NOW)) == 18
    w = status(dict(TPV, leapseconds=19), PPS).warnings(NOW)
    assert list(w) == ["leap"] and "LEAP_SECONDS" in w["leap"]


def test_dictwrapper_like_reports():
    class Wrapper:                                       # gps.dictwrapper: get(), no dict subclass
        def __init__(self, d):
            self.d = d

        def get(self, k, default=None):
            v = self.d.get(k, default)
            return [Wrapper(x) for x in v] if isinstance(v, list) else v
    v = status(Wrapper(SKY)).values(NOW)
    assert v["gps_sats_used"] == 2


# --- housekeeping integration --------------------------------------------------------

def test_housekeeping_logs_gps_values_and_rate_limits_warnings(monkeypatch):
    import lib.HouseKeeping as hk_module
    h = HouseKeeping.__new__(HouseKeeping)
    h.log = logging.getLogger("test_hk_gps")
    h.gps_status = status(TPV, SKY, dict(PPS, clock_sec=PPS["clock_sec"] + 1))
    h.gps_warned = {}
    h.data = [{"dev": "gps", "name": n, "value": 0} for n in ("gps_sats_used", "gps_clock_offset")]
    monkeypatch.setattr(hk_module.time, "time", lambda: NOW)
    h.collect_data()
    assert h.data[0]["value"] == 2 and h.data[1]["value"] == pytest.approx(1.003)
    warnings = []
    h.log = types.SimpleNamespace(warning=warnings.append)
    h.check_gps_warnings()
    h.check_gps_warnings()                               # same hour: not repeated
    assert len(warnings) == 1
