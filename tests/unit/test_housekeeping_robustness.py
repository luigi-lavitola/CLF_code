"""HouseKeeping: the loop must survive readout errors and fail safe when the sensors cannot be read."""

import logging
import types

import pytest

import lib.HouseKeeping as hk_module
from lib.HouseKeeping import HouseKeeping

RAIN = {'dev': 'dio', 'name': 'rain', 'value': True, 'error': False, 'alarm': False}
DRY = {'dev': 'dio', 'name': 'rain', 'value': False, 'error': False, 'alarm': False}


class NoThread:
    def __init__(self, target):
        pass

    def start(self):
        pass

    def join(self):
        pass


@pytest.fixture
def hk(monkeypatch):
    monkeypatch.setattr(hk_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(hk_module.threading, "Thread", NoThread)
    h = HouseKeeping.__new__(HouseKeeping)          # no SPI / FTDI / gpsd
    h.log = logging.getLogger("test_hk")
    h.csv = logging.getLogger("test_hk_csv")
    h.data = [dict(DRY)]
    h.alarm_data = []
    h.running = False
    h.gpsd = types.SimpleNamespace(fix=types.SimpleNamespace(mode=3))
    HouseKeeping._HouseKeeping__subscribers.clear()
    yield h
    HouseKeeping._HouseKeeping__subscribers.clear()


def drive(hk, steps):
    """Run hk.run() for len(steps) cycles; each step is 'ok' or an exception raised by collect_data.
    Returns the alarm names received by a subscriber, one list per notification."""
    seen = []
    it = iter(steps)

    def collect():
        step = next(it, None)
        if step is None:
            hk.running = False                       # end the loop after the last step
        elif isinstance(step, Exception):
            raise step

    hk.collect_data = collect
    hk.log_data = lambda: None
    hk.subscribe(lambda alarms: seen.append([a['name'] for a in alarms]))
    hk.run()
    return seen


def test_loop_survives_and_fails_safe(hk):
    err = OSError("SPI timeout")
    seen = drive(hk, [err, err, err, err, "ok"])
    # first two failures: no alarm yet; from the third: fail-safe alarm at every failed cycle
    assert seen == [["housekeeping_error"], ["housekeeping_error"]]


def test_recovers_after_failures(hk):
    err = OSError("SPI timeout")
    drive(hk, [err, err, err, "ok"])
    assert hk.get_alarm() == []                     # sensors readable again and dry: no alarm


def test_single_glitch_does_not_alarm(hk):
    err = OSError("glitch")
    seen = drive(hk, [err, "ok", err, "ok"])
    assert seen == []


def test_check_alarm_never_exposes_empty_list(hk):
    """While check_alarm() runs, another thread calling get_alarm() must still see the rain alarm."""
    observed = []

    class Probe(dict):
        def get(self, key, default=None):
            observed.append([a['name'] for a in hk.get_alarm()])     # what the RunManager would see now
            return super().get(key, default)

    hk.data = [Probe(RAIN)]
    hk.check_alarm()                                 # previous cycle: raining
    observed.clear()
    hk.data = [Probe(RAIN)]
    hk.check_alarm()                                 # still raining
    assert observed and all(names == ["rain"] for names in observed)
    assert [a['name'] for a in hk.get_alarm()] == ["rain"]


def test_failing_subscriber_does_not_stop_others(hk):
    got = []

    def bad(alarms):
        raise RuntimeError("boom")
    hk.subscribe(bad)
    hk.subscribe(lambda alarms: got.append(alarms))
    hk.notify_subscribers([{"name": "rain"}])
    assert got == [[{"name": "rain"}]]


def test_gps_thread_survives_gpsd_errors(hk):
    calls = {"n": 0}

    def next_():
        calls["n"] += 1
        if calls["n"] < 3:
            raise StopIteration
        hk.running = False                          # recovered: stop the test loop

    hk.gpsd.next = next_
    hk.running = True
    hk.collect_gps()
    assert calls["n"] == 3
