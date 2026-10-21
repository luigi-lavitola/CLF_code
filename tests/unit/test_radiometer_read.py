"""Radiometer.read_power(): one triggered value per shot, NaN on error, never the next shot's value."""

import math

import pytest

import lib.Radiometer as rad_module
from lib.Radiometer import Radiometer3700, RadiometerOphir


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t


class Serial:
    """Delivers (arrival_time, bytes) items; read_until returns what arrived by the timeout."""
    is_open = True

    def __init__(self, clock, items):
        self.clock = clock
        self.items = list(items)
        self.timeout = 0.2

    def read_until(self, terminator):
        deadline = self.clock.t + self.timeout
        if self.items and self.items[0][0] <= deadline:
            t, data = self.items.pop(0)
            self.clock.t = max(self.clock.t, t)
            return data
        self.clock.t = deadline                # nothing arrived: timeout
        return b""

    def reset_input_buffer(self):
        self.items = [(t, d) for t, d in self.items if t > self.clock.t]

    def reset_output_buffer(self):
        pass


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rad_module, "_now", c.now, raising=False)
    return c


def make(cls, clock, items, ready=True):
    r = object.__new__(cls)
    r.serial = Serial(clock, items)
    r.ready = ready
    r.messages = []
    r.log = lambda level, msg: r.messages.append(msg)
    return r


def test_value(clock):
    assert make(Radiometer3700, clock, [(0.1, b"1.234\r")]).read_power() == 1.234


def test_line_split_by_timeout_is_not_cut(clock):
    # "1.2" arrives, the rest after the serial timeout: must read 1.234, not 1.2
    r = make(Radiometer3700, clock, [(0.1, b"1.2"), (0.5, b"34\r")])
    assert r.read_power() == 1.234


def test_timeout_gives_nan(clock):
    r = make(Radiometer3700, clock, [])
    assert math.isnan(r.read_power())
    assert clock.t == pytest.approx(Radiometer3700.READ_TIMEOUT_S)
    assert any("no value" in m for m in r.messages)


def test_missing_shot_does_not_take_next_value(clock):
    # shot 1 gives no reading; shot 2's value arrives 1 s later
    r = make(Radiometer3700, clock, [(1.1, b"2.000\r")])
    assert math.isnan(r.read_power())          # shot 1
    assert r.read_power() == 2.0               # shot 2 gets its own value


def test_unexpected_line_skipped(clock):
    r = make(Radiometer3700, clock, [(0.05, b"OK\r"), (0.1, b"0.5\r")])
    assert r.read_power() == 0.5
    assert any("skipped" in m for m in r.messages)


def test_not_ready_gives_nan(clock):
    assert math.isnan(make(Radiometer3700, clock, [(0.1, b"1.0\r")], ready=False).read_power())


@pytest.mark.parametrize("line,expected", [(b"*1.5E-3\r", 1.5e-3), (b"*3.25\r", 3.25)])
def test_ophir_value(clock, line, expected):
    assert make(RadiometerOphir, clock, [(0.1, line)]).read_power() == expected


def test_ophir_errors_are_nan_not_strings(clock):
    # old code returned the raw string (e.g. '' on timeout)
    r = make(RadiometerOphir, clock, [(0.1, b"?ERR\r")])
    assert math.isnan(r.read_power())


def test_flush_drops_stale_reading_and_partial_line(clock):
    r = make(Radiometer3700, clock, [(0.0, b"9.9\r")])
    r._rx = b"7."                               # partial line from an aborted read
    r.flush_buffers()
    r.serial.items = [(0.2, b"1.0\r")]
    assert r.read_power() == 1.0
