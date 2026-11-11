"""GpsInfo: values from gpsd TPV / SKY / PPS reports, and timestamp-related warnings."""

import logging
import math
import time
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


def test_dop_only_sky_does_not_hide_satellites():
    # gpsd 3.25 + u-blox in UBX mode: SKY with the satellites, then SKY with the DOPs only
    sky_dop = {"class": "SKY", "hdop": 1.2, "tdop": 1.5}
    v = status(dict(SKY, nSat=23, uSat=10), sky_dop).values(NOW)
    assert v["gps_sats_used"] == 10 and v["gps_sats_visible"] == 23
    assert v["gps_snr_mean"] == 41.0
    assert v["gps_hdop"] == 1.2 and v["gps_tdop"] == 1.5      # DOPs from the newest SKY


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


# --- UBX messages via gpsd raw=1 (hex dumps) ------------------------------------------------

import struct

from lib.Ubx import ubx_frame


def timegps(tacc=7, valid=0x07, leap=18):
    return ubx_frame(0x01, 0x20, struct.pack("<IihbBI", 402343000, 0, 2442, leap, valid, tacc))


def smgr(src=1):
    return ubx_frame(0x0A, 0x2E, bytes(4) + struct.pack("<IHHBBBB", 0, 0x0070, 0x0003, src, 1, 0, 0))


def clock(drift=1):
    return ubx_frame(0x01, 0x22, struct.pack("<IiiII", 0, 242380, drift, 7, 164))


def monhw(agc=3666, jam=20):
    p = bytearray(60)
    struct.pack_into("<HH", p, 16, 101, agc)
    p[20], p[21], p[45] = 1, 2, jam
    return ubx_frame(0x0A, 0x09, bytes(p))


def raw_status(*frames, at=NOW):
    s = GpsStatus()
    for f in frames:
        s.update_raw(f.hex() + "\r\n", at)
    return s


def test_ubx_values_from_hex_dumps():
    v = raw_status(timegps(), smgr(), clock(), monhw()).values(NOW)
    assert v["gps_tacc_ns"] == 7 and v["gps_time_valid"] == 1 and v["gps_holdover"] == 0
    assert v["gps_osc_drift"] == 1 and v["gps_agc"] == 3666 and v["gps_jam"] == 20


def test_ubx_missing_or_stale_is_nan():
    assert math.isnan(GpsStatus().values(NOW)["gps_tacc_ns"])
    v = raw_status(timegps(), at=NOW - 60).values(NOW)
    assert math.isnan(v["gps_tacc_ns"])


def test_ubx_frame_split_and_other_lines():
    s = GpsStatus()
    h = smgr(src=0).hex()
    s.update_raw("$GNRMC,154527.00,A,4050.28,N,01410.97,E,0.0,,291026,,,A*7B\r\n", NOW)   # NMEA: ignored
    s.update_raw(h[:20], NOW)
    s.update_raw(h[20:], NOW)
    s.update_raw("not hex at all", NOW)
    assert s.values(NOW)["gps_holdover"] == 1


def test_ubx_bad_checksum_ignored():
    f = bytearray(timegps(tacc=5))
    f[-1] ^= 0xFF
    assert math.isnan(raw_status(bytes(f)).values(NOW)["gps_tacc_ns"])


def test_ubx_warnings():
    assert raw_status(timegps(), smgr(), monhw()).warnings(NOW) == {}
    w = raw_status(timegps(tacc=80), smgr(src=0), monhw(jam=200)).warnings(NOW)
    assert set(w) == {"holdover", "tacc", "jam"} and "internal" in w["holdover"]


def test_housekeeping_raw_line_does_not_refresh_old_report(monkeypatch):
    """gps.next() returns the previous JSON report again for a raw line: it must not be
    stored as a new TPV (the fix age / staleness would be wrong)."""
    import lib.HouseKeeping as hk_module
    h = HouseKeeping.__new__(HouseKeeping)
    h.log = logging.getLogger("test_hk_gps_raw")
    h.gps_status = GpsStatus()
    h.gps_status.update(TPV, NOW - 60)
    lines = iter([smgr(src=0).hex() + "\r\n"])
    h.running = True

    def next_():
        try:
            h.gpsd.response = next(lines)
        except StopIteration:
            h.running = False
            raise RuntimeError("done")
        return TPV                          # stale JSON report, as the gps client does
    h.gpsd = types.SimpleNamespace(next=next_, response="")
    monkeypatch.setattr(hk_module.time, "sleep", lambda s: setattr(h, "running", False))
    h.GPS_RETRY_S = 1
    h.collect_gps()
    assert h.gps_status.reports["TPV"][0] == NOW - 60          # not refreshed
    assert h.gps_status.values(time.time())["gps_holdover"] == 1
