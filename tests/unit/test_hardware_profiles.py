"""Hardware profiles: conversions, parameters.yml handling and the FPGA registers written by the runs."""

import datetime

import pytest

import lib.Run as run_module
from lib.Hardware import PROFILES, get_profile, trigger_delay_ticks, check_firmware
from lib.Run import RunFD, RunTank, RunCalib, RunRaman
from lib.FPGAData import FPGAData

from fakes import FakeDC

V1, V2 = PROFILES[1], PROFILES[2]


def params(site="clf", **keys):
    return {"identity": site, site: {"tank_name": "celeste", **keys}}


CLF_V1 = params(hw_version=1, fd_trigger_ms=249.99411, tank_trigger_ms=499.99411)
CLF_V2 = params(hw_version=2, fd_trigger_ms=249.99411, tank_trigger_ms=499.99411)
CLF_OLD = params(fd_pps_delay=24982000, tank_pps_delay=49982000)      # site file before hw_version


# --- profile arithmetic ---------------------------------------------------------------

def test_tick_period():
    assert V1.tick_ns == 10.0
    assert V2.tick_ns == pytest.approx(8.138020833)


@pytest.mark.parametrize("hw", [V1, V2])
def test_pps_delay_inverts_trigger_time(hw):
    e = hw.ticks(174e-6)
    for t in (0.24999411, 0.34999411, 0.49999411, 0.69999411):
        d = hw.pps_delay(t, e)
        assert hw.trigger_time(d, e) == pytest.approx(t, abs=hw.seconds(1) / 2)


def test_period_compensates_v1_firmware():
    assert V1.period(1.0) == 99_999_998          # firmware v1 adds 2 ticks per period
    assert V2.period(1.0) == 122_880_000


def test_too_early_trigger_rejected():
    with pytest.raises(ValueError):
        V2.pps_delay(100e-6, V2.ticks(174e-6))


# --- parameters.yml --------------------------------------------------------------------

def test_missing_hw_version_defaults_to_v1():
    assert get_profile(CLF_OLD) is V1


def test_unknown_hw_version():
    with pytest.raises(ValueError):
        get_profile(params(hw_version=7))


def test_old_tick_keys_still_work_on_v1():
    assert trigger_delay_ticks(CLF_OLD, "fd", 17_400) == 24_982_000
    assert trigger_delay_ticks(CLF_OLD, "tank", 17_400) == 49_982_000


def test_old_tick_keys_refused_on_v2():
    with pytest.raises(ValueError):
        trigger_delay_ticks(params(hw_version=2, fd_pps_delay=24982000), "fd", 21_381)


def test_new_keys_reproduce_v1_values():
    assert trigger_delay_ticks(CLF_V1, "fd", 17_400) == 24_982_000
    assert trigger_delay_ticks(CLF_V1, "tank", 17_400) == 49_982_000
    xlf = params("xlf", hw_version=1, fd_trigger_ms=349.99411, tank_trigger_ms=699.99411)
    assert trigger_delay_ticks(xlf, "fd", 17_400) == 34_982_000
    assert trigger_delay_ticks(xlf, "tank", 17_400) == 69_982_000


def test_missing_trigger_key():
    with pytest.raises(KeyError):
        trigger_delay_ticks(params(hw_version=2), "fd", 21_381)


# --- firmware version register --------------------------------------------------------

class RegFPGA:
    def __init__(self, value):
        self.value = value

    def read_register(self, name):
        assert name == "fw_version"
        return self.value


def test_firmware_check():
    assert check_firmware(RegFPGA(0), V2) is None       # register not implemented: cannot check
    assert check_firmware(RegFPGA(2), V2) == 2
    with pytest.raises(RuntimeError):
        check_firmware(RegFPGA(2), V1)


# --- registers written by the runs ----------------------------------------------------

@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(run_module.TimeSync, "ensure", lambda fpga, log: True)   # tested in test_gps_time


def registers_after_prepare(run_class, p):
    dc = FakeDC(dio={"cover_raman_open": True})       # Raman cover opens at once
    run = run_class(dc, p)
    assert run.prepare() == 0
    r = dc.fpga.registers
    return {k: r[k] for k in ("pps_delay", "pulse_width", "pulse_energy", "pulse_period", "shots_num")}


# values hard-coded before the profiles existed (pulse_period aside, see below)
OLD_V1 = {
    RunFD:    dict(pps_delay=24_982_000, pulse_width=10_000, pulse_energy=17_400, shots_num=50),
    RunTank:  dict(pps_delay=49_982_000, pulse_width=10_000, pulse_energy=17_400, shots_num=3),
    RunCalib: dict(pps_delay=0,          pulse_width=10_000, pulse_energy=17_400, shots_num=15),
    RunRaman: dict(pps_delay=0,          pulse_width=10_000, pulse_energy=17_400, shots_num=75_000),
}
PERIOD_S = {RunFD: 1.0, RunTank: 1.0, RunCalib: 1.0, RunRaman: 10e-3}


@pytest.mark.parametrize("p", [CLF_V1, CLF_OLD], ids=["new keys", "old keys"])
@pytest.mark.parametrize("run_class", list(OLD_V1))
def test_v1_registers_unchanged(run_class, p):
    regs = registers_after_prepare(run_class, p)
    period = regs.pop("pulse_period")
    assert regs == OLD_V1[run_class]
    # only change on v1: P-2 written so that the real period (P+2) is exact
    assert period == round(PERIOD_S[run_class] * 1e8) - 2


@pytest.mark.parametrize("run_class", list(OLD_V1))
def test_v2_registers(run_class):
    regs = registers_after_prepare(run_class, CLF_V2)
    assert regs["pulse_width"] == 12_288              # 100 us
    assert regs["pulse_energy"] == 21_381             # 174 us
    assert regs["pulse_period"] == round(PERIOD_S[run_class] * 122.88e6)
    assert regs["shots_num"] == OLD_V1[run_class]["shots_num"]


@pytest.mark.parametrize("run_class,trigger_ms", [(RunFD, 249.99411), (RunTank, 499.99411)])
def test_same_physical_trigger_time_on_v1_and_v2(run_class, trigger_ms):
    t1 = V1.trigger_time(registers_after_prepare(run_class, CLF_V1)["pps_delay"], 17_400)
    t2 = V2.trigger_time(registers_after_prepare(run_class, CLF_V2)["pps_delay"], 21_381)
    assert t1 * 1e3 == pytest.approx(trigger_ms, abs=1e-5)
    assert t2 == pytest.approx(t1, abs=V2.seconds(1))  # within one v2 tick (8.1 ns)


# --- timestamp packet -----------------------------------------------------------------

@pytest.mark.parametrize("hw", [V1, V2])
def test_packet_uses_profile_tick(hw):
    data = object.__new__(FPGAData)
    data._setup(hw.tick_ns)
    data.buffer = "BAAB\r6774\r8580\r017D\r761A\r7FFD\r0001\rFEEF\r"
    p = data._next_frame()
    assert p.seconds == 1_735_689_600 and p.shot == 1
    assert p.counter == pytest.approx(24_999_450 * hw.tick_ns)
    assert p.pps_delta == pytest.approx(-2 * hw.tick_ns)


def test_build_time_decoding():
    from lib.Hardware import decode_build_time
    # 2026-10-29 12:34:56 packed as USR_ACCESS TIMESTAMP
    v = (29 << 27) | (10 << 23) | (26 << 17) | (12 << 12) | (34 << 6) | 56
    assert decode_build_time(v) == datetime.datetime(2026, 10, 29, 12, 34, 56)
    assert decode_build_time(0) is None                  # firmware without the register
    assert decode_build_time(0xFFFFFFFF) is None         # impossible date
