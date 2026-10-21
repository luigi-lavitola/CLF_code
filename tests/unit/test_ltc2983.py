"""LTC2983 temperature conversion: sign, fault bits, conversion timeout."""

import math

import pytest

import lib.LTC2983 as ltc_module
from lib.LTC2983 import LTC2983_Base
from lib.LTC2983_const import READ_CH_BASE


class FakeLTC(LTC2983_Base):
    """Register-level model: conversion done after `polls` status reads (None = never)."""

    def __init__(self, result, polls=2):
        self.result = result
        self.polls = polls
        self.writes = []
        self._count = 0

    def write_register(self, addr, value, nbytes=1):
        self.writes.append((addr, value, nbytes))
        self._count = 0

    def read_register(self, addr, nbytes=1):
        if addr == self.Register.COMMAND_STATUS:
            self._count += 1
            done = self.polls is not None and self._count > self.polls
            return 0x40 if done else 0x80
        assert nbytes == 4 and addr >= READ_CH_BASE
        return self.result


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(ltc_module, "sleep", lambda s: None)


def raw(temp_c, fault=0x01):
    return (fault << 24) | (int(round(temp_c * 1024)) & 0xFFFFFF)


@pytest.mark.parametrize("t", [21.5, 0.0, -0.5, -5.0, -12.25, -40.0, 85.0])
def test_temperature_sign(t):
    # old code: -0.5 C was read as 4194303.5 C
    assert FakeLTC(raw(t)).read_temperature(4) == pytest.approx(t)


@pytest.mark.parametrize("fault", [0x00, 0x81, 0x41])   # not valid, sensor hard fault, ADC hard fault
def test_invalid_result_is_nan(fault):
    assert math.isnan(FakeLTC(raw(20.0, fault)).read_temperature(4))


def test_soft_fault_keeps_value():
    # bit 27 (sensor over range) is a soft fault: the value is still reported
    assert FakeLTC(raw(20.0, 0x09)).read_temperature(4) == pytest.approx(20.0)


def test_conversion_timeout_raises():
    # old code: endless loop, housekeeping thread blocked without any exception
    with pytest.raises(TimeoutError):
        FakeLTC(raw(20.0), polls=None).read_channel(4)


def test_conversion_started_on_the_right_channel():
    f = FakeLTC(raw(20.0))
    f.read_channel(6)
    assert f.writes[0] == (f.Register.COMMAND_STATUS, 0x80 | 6, 1)


def test_write_register_explicit_byteorder():
    from lib.LTC2983 import LTC2983_FTDI

    class Spi:
        def write(self, data):
            self.data = data
    dev = object.__new__(LTC2983_FTDI)
    dev.spi = Spi()
    dev.write_register(0x0204, 0x12345678, 4)
    assert dev.spi.data == [0x02, 0x02, 0x04, 0x12, 0x34, 0x56, 0x78]
