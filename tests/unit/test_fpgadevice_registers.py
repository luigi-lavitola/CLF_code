"""FPGADevice name -> register/bit mapping against the firmware register map (Run_Control.vhd)."""

import pytest

import lib.FPGADevice as fpga_module
from lib.FPGADevice import FPGADevice


class FirmwareModel:
    """Read side of Run_Control: 0x07 status bits, 0x0D/0x0E latched Time_Tag."""

    def __init__(self, pps_present=True, time_tag=0):
        self.pps_present = pps_present
        self.time_tag = time_tag
        self.latched = 0

    def read(self, addr):
        if addr == 0x07:        # "0000000" & PPS_PRESENT & Freq_10M_OK & Freq_Back_OK(7 downto 1)
            return int(self.pps_present) << 8
        if addr == 0x0D:
            self.latched = (self.time_tag >> 11) & 0xFFFF      # RC_TimeR <= RC_Time(26 downto 11)
            return self.time_tag & 0xFFFF
        if addr == 0x0E:
            return self.latched
        return 0


@pytest.fixture
def make_fpga(monkeypatch):
    monkeypatch.setattr(fpga_module.serial, "Serial", lambda *a, **k: object())

    def make(model):
        monkeypatch.setattr(FPGADevice, "_FPGADevice__instance", None)    # singleton
        dev = FPGADevice("/dev/null")
        dev.read_address = model.read
        return dev
    return make


@pytest.mark.parametrize("present", [True, False])
def test_pps_flags_read_pps_present(make_fpga, present):
    dev = make_fpga(FirmwareModel(pps_present=present))
    assert dev.read_dio("pps_present") is present
    assert dev.read_dio("pps_ok") is present


@pytest.mark.parametrize("tick", [0, 0x7FF, 0x800, 24_999_450, 99_999_999, 2 ** 27 - 1])
def test_time_cnt(make_fpga, tick):
    dev = make_fpga(FirmwareModel(time_tag=tick))
    assert dev.read_register("time_cnt") == tick
