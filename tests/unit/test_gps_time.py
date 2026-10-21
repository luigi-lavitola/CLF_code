"""GPS time conversion and FPGA seconds counter alignment."""

import pytest

import lib.Run as run_module
from lib.GpsTime import unix_to_gps, gps_to_unix, gps_utc_offset
from lib import TimeSync
from lib.Run import RunFD
from lib.FPGAData import Packet

from fakes import FakeDC


# --- conversion -----------------------------------------------------------------------

@pytest.mark.parametrize("unix,gps", [
    (315_964_800, 0),                        # GPS epoch 1980-01-06
    (1_735_689_600, 1_419_724_818),          # 2025-01-01 00:00:00 UTC
])
def test_known_values(unix, gps):
    assert unix_to_gps(unix) == gps
    assert gps_to_unix(gps) == unix


def test_leap_second_2017():
    assert gps_utc_offset(1_483_228_799) == 17   # 2016-12-31 23:59:59
    assert gps_utc_offset(1_483_228_800) == 18   # 2017-01-01 00:00:00
    # across the leap second GPS advances by 2 for 1 UNIX second
    assert unix_to_gps(1_483_228_800) - unix_to_gps(1_483_228_799) == 2


# --- FPGA counter model ---------------------------------------------------------------

class Clock:
    """Fake host clock: sleep() advances now()."""
    def __init__(self, t, host_error=0.0):
        self.t = t
        self.host_error = host_error         # host clock - true UTC

    def now(self):
        return self.t + self.host_error

    def sleep(self, s):
        self.t += s


class FPGACounter:
    """Seconds counter as in Time_Tag_Gen: loaded at once on write, +1 at every true PPS."""
    def __init__(self, clock, value_at_t0, pps=True):
        self.clock = clock
        self.base_t = int(clock.t)
        self.base_value = value_at_t0
        self.pps = pps
        self.writes = []
        self.last_written = None

    def read_register(self, name):
        assert name == 'unixtime'
        if not self.pps:
            return self.base_value                  # no PPS: the counter does not advance
        return self.base_value + int(self.clock.t) - self.base_t

    def write_register(self, name, value):
        assert name == 'arm_unixtime'
        self.writes.append((self.clock.t, value))
        self.clock.sleep(0.25)               # two serial writes ~0.1 s each + margin
        if value != self.last_written:       # firmware loads only a different value
            self.base_t, self.base_value = int(self.clock.t), value
        self.last_written = value


def run_ensure(fpga_offset, host_error=0.0, start=1_735_689_600.73, pps=True):
    clock = Clock(start, host_error)
    fpga = FPGACounter(clock, int(start) + fpga_offset, pps)
    messages = []
    ok = TimeSync.ensure(fpga, lambda lvl, m: messages.append(lvl), now=clock.now, sleep=clock.sleep)
    return ok, fpga, messages, clock


def test_already_aligned_no_write():
    ok, fpga, msgs, _ = run_ensure(0)
    assert ok and fpga.writes == [] and msgs == ['info']


@pytest.mark.parametrize("off", [-3600, -1, 1, 37])
def test_misaligned_counter_is_fixed(off):
    ok, fpga, msgs, clock = run_ensure(off)
    assert ok and len(fpga.writes) == 1
    assert fpga.read_register('unixtime') == int(clock.t)
    t, _ = fpga.writes[0]
    assert 0.1 < t % 1 < 0.2                 # written right after a second boundary


def test_missing_pps_reported():
    ok, fpga, msgs, _ = run_ensure(-5, pps=False)
    assert not ok and msgs[-1] == 'error' and len(fpga.writes) == 3


@pytest.mark.parametrize("host_error", [-0.04, 0.04])
def test_small_host_clock_error_is_fine(host_error):
    # NTP-level error (tens of ms) is well within the write window
    ok, fpga, _, _ = run_ensure(7, host_error=host_error)
    assert ok


# --- run log --------------------------------------------------------------------------

def test_shot_log_uses_gps_seconds(monkeypatch):
    class Data:
        def read_shot(self, n, timeout_s):
            return Packet(1_735_689_600, 249_994_500, -20, n, "")
    dc = FakeDC()
    dc.data = Data()
    run = RunFD(dc, {"identity": "clf", "clf": {}})
    lines = []
    run.log = lambda lvl, msg, **kw: lines.append(msg)
    run.log_shot(0, 'Rad1')
    assert "gps_seconds: 1419724818," in lines[0]


def test_shot_log_failed_read_stays_zero():
    class Data:
        def read_shot(self, n, timeout_s):
            return None                      # no packet for this shot
    dc = FakeDC()
    dc.data = Data()
    run = RunFD(dc, {"identity": "clf", "clf": {}})
    lines = []
    run.log = lambda lvl, msg, **kw: lines.append(msg)
    run.log_shot(0, 'Rad1')
    assert "gps_seconds: 0," in lines[0]
