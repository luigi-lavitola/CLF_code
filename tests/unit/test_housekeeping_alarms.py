"""HouseKeeping.check_alarm() with the real sensor configuration files of CLF and XLF."""

import copy
import logging
import os
import types

import pytest
import yaml

from lib.HouseKeeping import HouseKeeping
from lib.GpsInfo import GpsStatus

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_sensors(identity):
    with open(os.path.join(ROOT, "conf", identity, "sensors.yml")) as f:
        return [e for doc in yaml.safe_load_all(f) for e in doc]


def make_hk(identity, gps_mode=3):
    h = HouseKeeping.__new__(HouseKeeping)
    h.log = logging.getLogger("test_hk")
    h.data = copy.deepcopy(load_sensors(identity))
    h.alarm_data = []
    h.gpsd = types.SimpleNamespace(fix=types.SimpleNamespace(mode=gps_mode))
    h.gps_fix_str = ["unknown", "no fix", "2D", "3D"]
    h.gps_status = GpsStatus()
    h.gps_warned = {}
    return h


def set_values(h, rain):
    """Readout values within limits, with or without rain (as collect_data() would leave them)."""
    for d in h.data:
        if d['dev'] == 'tla':
            d['value'] = bool(rain) if d['name'] == 'rain' else (d['min'] + d['max']) / 2 if 'min' in d else 12.0
        elif d['dev'] == 'dio':
            d['value'] = bool(rain) if d['name'] == 'rain' else False
            if d['name'] == 'rain':
                d['error'] = False


@pytest.mark.parametrize("identity", ["clf", "xlf"])
def test_every_configured_alarm_can_be_evaluated(identity):
    h = make_hk(identity)
    set_values(h, rain=False)
    h.check_alarm()                                  # must not raise (KeyError on min/max, ...)
    assert h.get_alarm() == []


@pytest.mark.parametrize("identity", ["clf", "xlf"])
def test_rain_raises_alarm(identity):
    h = make_hk(identity)
    set_values(h, rain=True)
    h.check_alarm()
    rain_enabled = "alarm" in [d for d in load_sensors(identity) if d['name'] == 'rain'][0]
    # CLF: rain alarm disabled in conf/clf/sensors.yml (as on site)
    assert ("rain" in [a['name'] for a in h.get_alarm()]) is rain_enabled


@pytest.mark.parametrize("identity", ["clf", "xlf"])
@pytest.mark.parametrize("mode,pps,alarm", [
    (3, True, False),       # 3D fix + PPS: ok
    (2, True, False),       # 2D fix is enough for timing
    (1, True, True),        # gpsd: no fix
    (0, True, True),        # gpsd: unknown
    (3, False, True),       # fix but the FPGA does not see the PPS
])
def test_gps_alarm(identity, mode, pps, alarm):
    h = make_hk(identity, gps_mode=mode)
    h.fpga = types.SimpleNamespace(read_dio=lambda name: {"pps_present": pps}[name],
                                   read_register=lambda name: {"pps_distance": 32765}[name])
    h.data = [d for d in h.data if d['dev'] == 'gps']        # collect only the gps entry
    h.collect_data()
    h.check_alarm()
    assert ("gps_fix" in [a['name'] for a in h.get_alarm()]) is alarm


@pytest.mark.parametrize("identity", ["clf", "xlf"])
def test_battery_out_of_range(identity):
    h = make_hk(identity)
    set_values(h, rain=False)
    battery = next(d for d in h.data if d['name'] == 'battery1')
    battery['value'] = battery['min'] - 0.5
    h.check_alarm()
    assert [a['name'] for a in h.get_alarm()] == ["battery1"]
