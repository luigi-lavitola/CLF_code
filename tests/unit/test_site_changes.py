"""Changes that were running only on the site PCs (2026-10-22), now in the repo."""

import copy
import logging
import os
import types

import pytest
import yaml

import lib.FPGADevice as fpga_module
from lib.FPGADevice import FPGADevice
from lib.GpsInfo import GpsStatus
from lib.HouseKeeping import HouseKeeping
from lib import TimeSync

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sensors(site):
    with open(os.path.join(ROOT, "conf", site, "sensors.yml")) as f:
        return [e for doc in yaml.safe_load_all(f) for e in doc]


# --- CLF DB25 wiring -----------------------------------------------------------------------

@pytest.fixture
def fpga(monkeypatch):
    monkeypatch.setattr(fpga_module.serial, "Serial", lambda *a, **k: object())
    monkeypatch.setattr(FPGADevice, "_FPGADevice__instance", None)
    return FPGADevice("/dev/null")


def test_clf_dio_map(fpga):
    with open(os.path.join(ROOT, "conf", "clf", "dio.yml")) as f:
        fpga.apply_dio_map(yaml.safe_load(f))
    m = fpga.iomap
    assert (m["rain"].regaddr, m["rain"].bit) == (0x16, 2)
    assert (m["norain"].regaddr, m["norain"].bit) == (0x16, 3)
    assert (m["cover_steer_closed"].bit, m["cover_steer_closed"].inverted) == (4, True)
    assert (m["cover_steer_open"].bit, m["cover_steer_open"].inverted) == (5, True)
    assert m["cover_raman_open"].bit == 1                    # not overridden


def test_xlf_has_default_wiring():
    assert not os.path.exists(os.path.join(ROOT, "conf", "xlf", "dio.yml"))


def test_unknown_dio_name_rejected(fpga):
    with pytest.raises(NameError):
        fpga.apply_dio_map({"rian": [0x16, 2, False]})


# --- sensors --------------------------------------------------------------------------------

def test_clf_rain_alarm_disabled_by_config():
    rain = [d for d in sensors("clf") if d["name"] == "rain"][0]
    assert "alarm" not in rain
    assert "alarm" in [d for d in sensors("xlf") if d["name"] == "rain"][0]


@pytest.mark.parametrize("site", ["clf", "xlf"])
def test_gps_columns_order(site):
    names = [d["name"] for d in sensors(site)]
    i = names.index("gps_fix")
    # same order as on site (hk.csv has no header), new gpsd fields after
    assert names[i:i + 4] == ["gps_fix", "gps_ns_error", "gps_fix_age", "gps_sats_used"]


def make_hk(site, pps_distance=32765, tpv_time="2026-10-22T10:00:00.000Z", now=1792663205.0):
    h = HouseKeeping.__new__(HouseKeeping)
    h.log = logging.getLogger("test_hk")
    h.data = [copy.deepcopy(d) for d in sensors(site) if d["name"] in ("gps_ns_error", "gps_fix_age")]
    h.alarm_data = []
    h.tick_ns = 10.0
    h.gps_status = GpsStatus()
    if tpv_time:
        h.gps_status.update({"class": "TPV", "time": tpv_time}, now)
    h.fpga = types.SimpleNamespace(read_register=lambda name: {"pps_distance": pps_distance}[name])
    return h, now


@pytest.mark.parametrize("site", ["clf", "xlf"])
@pytest.mark.parametrize("pps_distance,tpv_time,age_s,expected", [
    (32765, "2026-10-22T10:00:00.000Z", 5, []),                          # -20 ns, fix 5 s old
    (32757, "2026-10-22T10:00:00.000Z", 5, []),                          # -100 ns: on the limit
    (32756, "2026-10-22T10:00:00.000Z", 5, ["gps_ns_error"]),            # -110 ns
    (0, "2026-10-22T10:00:00.000Z", 5, ["gps_ns_error"]),                # GPS PPS outside the window
    (32765, "2026-10-22T10:00:00.000Z", 120, ["gps_fix_age"]),           # fix 2 min old
    (32765, None, 0, ["gps_fix_age"]),                                   # no fix time at all
])
def test_gps_error_and_fix_age_alarms(monkeypatch, site, pps_distance, tpv_time, age_s, expected):
    import lib.HouseKeeping as hk_module
    fix = 1792663200.0                                                   # 2026-10-22T10:00:00Z
    h, now = make_hk(site, pps_distance, tpv_time, now=fix + age_s)
    monkeypatch.setattr(hk_module.time, "time", lambda: now)
    h.collect_data()
    h.check_alarm()
    assert [a["name"] for a in h.get_alarm()] == expected


# --- local PPS alignment ------------------------------------------------------------------------

class PpsFPGA:
    """pps_distance as the firmware: force align puts the local PPS ~5 ticks after the GPS one."""
    def __init__(self, d, gps_present=True):
        self.d = d
        self.gps_present = gps_present
        self.forced = 0

    def read_register(self, name):
        assert name == "pps_distance"
        return self.d

    def write_dio(self, name, value):
        assert name == "force_align" and value
        self.forced += 1
        if self.gps_present:
            self.d = 32768 - 5


@pytest.mark.parametrize("d,forced,ok", [
    (32765, 0, True),            # aligned (hw v1 PID): nothing done
    (50000, 1, True),            # hw v2 after power-up: arbitrary phase -> force align
    (0, 1, True),                # GPS PPS outside the measuring window
])
def test_ensure_pps(d, forced, ok):
    f = PpsFPGA(d)
    msgs = []
    assert TimeSync.ensure_pps(f, 8.138, lambda lvl, m: msgs.append(lvl), sleep=lambda s: None) is ok
    assert f.forced == forced


def test_ensure_pps_without_gps():
    f = PpsFPGA(50000, gps_present=False)
    msgs = []
    assert TimeSync.ensure_pps(f, 8.138, lambda lvl, m: msgs.append(lvl), sleep=lambda s: None) is False
    assert msgs[-1] == "error"
