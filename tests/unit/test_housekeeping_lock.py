"""HouseKeeping: FPGA register 0x27 (sticky clock lock-lost bits) read and cleared every cycle."""

import logging
import math

from lib.HouseKeeping import HouseKeeping
from test_housekeeping_alarms import make_hk


class LockFPGA:
    """0x27 bit 0 sticky: set by lose(), cleared by any write."""
    def __init__(self, lost=True):          # set at power-up
        self.reg = int(lost)
        self.writes = 0

    def lose(self):
        self.reg = 1

    def read_register(self, name):
        assert name == "lock_lost"
        return self.reg | (self.reg << 1)   # single-MMCM firmware: bit1 = bit0

    def write_register(self, name, value):
        assert name == "lock_lost"
        self.reg = 0
        self.writes += 1


def hk(version=2, lost_at_start=True):
    h = make_hk("clf")
    h.hw_version = version
    h.fpga = LockFPGA(lost_at_start)
    h.data = [d for d in h.data if d['dev'] == 'fpga']
    return h


def value(h):
    h.collect_data()
    return h.data[0]['value']


def test_entry_configured_on_both_sites():
    for site in ("clf", "xlf"):
        assert [d['name'] for d in make_hk(site).data if d['dev'] == 'fpga'] == ['fpga_lock_lost']


def test_power_up_value_is_cleared_without_warning(caplog):
    h = hk()
    with caplog.at_level(logging.INFO):
        assert value(h) == 0
    assert h.fpga.reg == 0 and h.fpga.writes == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert value(h) == 0 and h.fpga.writes == 1         # nothing lost: no write


def test_loss_is_reported_cleared_and_rate_limited(caplog):
    h = hk()
    value(h)
    with caplog.at_level(logging.WARNING):
        h.fpga.lose()
        assert value(h) == 1 and h.fpga.reg == 0
        assert value(h) == 0
        h.fpga.lose()
        assert value(h) == 1                             # second loss within 10 min: no new warning
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "lost lock" in warnings[0]
    h.lock_warned -= HouseKeeping.LOCK_WARNING_PERIOD_S
    with caplog.at_level(logging.WARNING):
        h.fpga.lose()
        value(h)
    assert "2 cycle(s)" in caplog.records[-1].getMessage()  # the unreported one is counted


def test_hw_v1_has_no_register():
    h = hk(version=1)
    assert math.isnan(value(h)) and h.fpga.writes == 0


def test_alarm_only_when_enabled():
    h = hk()
    value(h)
    h.fpga.lose()
    value(h)
    h.check_alarm()
    assert h.get_alarm() == []                           # no 'alarm' key in sensors.yml
    h.data[0]['alarm'] = False
    h.check_alarm()
    assert [a['name'] for a in h.get_alarm()] == ['fpga_lock_lost']
