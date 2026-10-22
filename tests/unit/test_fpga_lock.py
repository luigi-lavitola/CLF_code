"""FPGADevice serial lock and read retries; RunManager terminates the run process safely."""

import multiprocessing
import threading

import pytest

import lib.FPGADevice as fpga_module
from lib.FPGADevice import FPGADevice
from lib.RunManager import RunManager
from lib import TimeSync


class Serial:
    def __init__(self, answers):
        self.answers = list(answers)      # bytes returned by read_until, one per request
        self.requests = 0

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.requests += 1

    def read_until(self, terminator):
        return self.answers.pop(0) if self.answers else b""


@pytest.fixture
def make_fpga(monkeypatch):
    monkeypatch.setattr(fpga_module.serial, "Serial", lambda *a, **k: Serial([]))

    def make(answers=()):
        monkeypatch.setattr(FPGADevice, "_FPGADevice__instance", None)
        dev = FPGADevice("/dev/null")
        dev.serial = Serial(answers)
        return dev
    return make


# --- read_address ---------------------------------------------------------------------

def test_read_ok(make_fpga):
    assert make_fpga([b"1234\r"]).read_address(0x16) == 0x1234


def test_read_retries_then_ok(make_fpga):
    dev = make_fpga([b"", b"zz\r", b"0042\r"])          # timeout, garbage, good
    assert dev.read_address(0x17) == 0x42 and dev.serial.requests == 3


def test_partial_answer_is_not_parsed(make_fpga):
    dev = make_fpga([b"12", b"0007\r"])                 # "12" without CR = timeout mid answer
    assert dev.read_address(0x17) == 7


def test_read_failure_raises_instead_of_zero(make_fpga):
    with pytest.raises(IOError):
        make_fpga([b"", b"", b""]).read_address(0x17)


def test_write_dio_does_not_clear_bits_on_read_failure(make_fpga):
    dev = make_fpga([])                                 # register 0x17 cannot be read
    written = []
    dev.write_address = lambda addr, value: written.append((addr, value))
    with pytest.raises(IOError):
        dev.write_dio("flipper_raman", True)
    assert written == []                                # old code wrote 0b100: inverter etc. off


# --- lock -------------------------------------------------------------------------------

def test_lock_released_on_exception(make_fpga):
    dev = make_fpga([])
    with pytest.raises(IOError):
        dev.read_address(0x0)
    assert dev.mutex.acquire(timeout=0.1)               # not left held
    dev.mutex.release()


def test_stuck_lock_raises_instead_of_deadlock(make_fpga, monkeypatch):
    dev = make_fpga([b"0001\r"])
    monkeypatch.setattr(FPGADevice, "LOCK_TIMEOUT_S", 0.2)
    dev.mutex.acquire()                                 # held by a dead process
    with pytest.raises(TimeoutError):
        dev.read_address(0x0)


# --- RunManager._terminate_job ------------------------------------------------------------

class Job:
    def __init__(self, mutex):
        self.mutex = mutex
        self.lock_free_at_terminate = None

    def terminate(self):
        # if the parent holds the lock, a non-blocking acquire from here fails
        got = self.mutex.acquire(block=False)
        if got:
            self.mutex.release()
        self.lock_free_at_terminate = got

    def join(self, timeout=None):
        pass

    def is_alive(self):
        return True


def make_rm(fpga):
    rm = RunManager.__new__(RunManager)
    rm.dc = type("DC", (), {"fpga": fpga})()
    rm.log = lambda *a, **k: None
    return rm


def test_terminate_takes_the_lock_first(make_fpga):
    dev = make_fpga()
    rm = make_rm(dev)
    rm.job = Job(dev.mutex)
    rm._terminate_job()
    assert rm.job.lock_free_at_terminate is False       # parent held it: child not mid-transaction
    assert dev.mutex.acquire(timeout=0.1)               # and released it afterwards
    dev.mutex.release()


def test_terminate_with_lock_held_by_stuck_child(make_fpga, monkeypatch):
    dev = make_fpga()
    monkeypatch.setattr(FPGADevice, "LOCK_TIMEOUT_S", 0.2)
    old = dev.mutex
    old.acquire()                                       # stuck child holds it
    rm = make_rm(dev)
    rm.job = Job(old)
    rm._terminate_job()
    assert dev.mutex is not old                         # replaced: the parent can go on
    assert dev.mutex.acquire(timeout=0.1)
    dev.mutex.release()


def test_alarm_handler_resets_flag_when_abort_fails(make_fpga):
    dev = make_fpga()
    rm = make_rm(dev)
    rm.job = Job(dev.mutex)
    rm.abort_in_progress = False

    class Run:
        def abort(self):
            raise IOError("FPGA not answering")
    rm.run = Run()
    with pytest.raises(IOError):
        rm.alarm_handler([{"name": "rain"}])
    assert rm.abort_in_progress is False                # next alarms are still handled


def test_time_sync_reports_fpga_failure():
    class Dead:
        def read_register(self, name):
            raise IOError("no answer")
    msgs = []
    ok = TimeSync.ensure(Dead(), lambda lvl, m: msgs.append(lvl), now=lambda: 0.6, sleep=lambda s: None)
    assert ok is False and msgs == ["error"]
