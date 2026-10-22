"""Station shutdown when no run is coming (auto mode) or on an alarm between runs."""

import datetime

import pytest

import lib.Run as run_module
import lib.RunManager as rm_module
from lib.Run import RunShutdown, RunType
from lib.RunCalendar import RunEntry
from lib.RunManager import RunManager

from fakes import FakeDC

CLF_OUTLETS = ["RAMAN_inst", "radiometer", "laser", "RAMAN_cover", "Vert_cover", "VXM"]
XLF_OUTLETS = ["VXM", "radiometer", "laser", "Vert_cover", "steering"]


def station(outlets, inverter=True):
    dc = FakeDC(dio={"inverter": inverter, "cover_raman_closed": True})
    for name in outlets:
        dc.get_outlet(name).state = True
    return dc


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)


# --- RunShutdown ------------------------------------------------------------------------

def test_shutdown_clf():
    dc = station(CLF_OUTLETS)
    RunShutdown(dc, {"identity": "clf", "clf": {}}).execute()
    ev = dc.events
    assert ev[0] == ("dio", "laser_en", False)
    assert ("laser", "standby") in ev
    for name in ("RAMAN_inst", "radiometer", "laser", "RAMAN_cover", "Vert_cover", "VXM"):
        assert dc.outlets[name].state is False
    assert ev.index(("outlet_off", "Vert_cover")) < ev.index(("dio", "inverter", False))
    assert ev[-1] == ("dio", "inverter", False)


def test_shutdown_xlf_only_its_outlets():
    dc = station(XLF_OUTLETS)
    RunShutdown(dc, {"identity": "xlf", "xlf": {}}).execute()
    assert "RAMAN_cover" not in dc.outlets and "RAMAN_inst" not in dc.outlets
    assert dc.outlets["steering"].state is True        # not a shutdown outlet
    assert dc.events[-1] == ("dio", "inverter", False)


def test_shutdown_idempotent_when_off():
    dc = station(CLF_OUTLETS, inverter=False)
    RunShutdown(dc, {"identity": "clf", "clf": {}}).execute()
    assert dc.events == []


# --- RunManager decisions ---------------------------------------------------------------

class FakeProcess:
    def __init__(self, target, args=()):
        self.target = target
        self.alive = False

    def start(self):
        self.alive = True

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.alive = False

    def join(self, timeout=None):
        pass


@pytest.fixture
def make_rm(monkeypatch):
    monkeypatch.setattr(rm_module.multiprocessing, "Process", FakeProcess)

    def make(inverter=True, next_in_min=None, auto=True):
        rm = RunManager.__new__(RunManager)
        rm.dc = station(CLF_OUTLETS, inverter)
        rm.params = {"identity": "clf", "clf": {}}
        rm.scheduler_running = auto
        rm.job = rm.run = rm.runentry = None
        rm.abort_in_progress = False
        rm.messages = []
        rm.log = lambda level, msg, **kw: rm.messages.append(msg)
        nr = None
        if next_in_min is not None:
            nr = RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=next_in_min), RunType.FD)
        rm.nr = nr
        return rm
    return make


def shutdown_started(rm):
    return rm.runentry is not None and rm.runentry.runtype == RunType.SHUTDOWN and rm.job.is_alive()


@pytest.mark.parametrize("next_in_min,expected", [
    (None, True),       # no run left in the calendar
    (60, True),         # next run tomorrow / far away
    (44, False),        # still within the night (e.g. Raman end+30 -> calib end+60)
    (14, False),        # between FD runs
])
def test_idle_rule(make_rm, next_in_min, expected):
    rm = make_rm(next_in_min=next_in_min)
    rm.idle_check(rm.nr)
    assert shutdown_started(rm) is expected


def test_idle_not_in_manual_mode(make_rm):
    rm = make_rm(auto=False)
    rm.idle_check(None)
    assert not shutdown_started(rm)


def test_idle_not_when_already_off(make_rm):
    rm = make_rm(inverter=False)
    rm.idle_check(None)
    assert not shutdown_started(rm)


def test_idle_not_while_a_job_runs(make_rm):
    rm = make_rm()
    rm.job = FakeProcess(None)
    rm.job.start()
    rm.idle_check(None)
    assert rm.runentry is None


def test_idle_checked_at_most_once_a_minute(make_rm):
    rm = make_rm(inverter=False)
    reads = []
    real = rm.dc.fpga.read_dio
    rm.dc.fpga.read_dio = lambda name: reads.append(name) or real(name)
    rm.idle_check(None)
    rm.idle_check(None)
    assert reads == ["inverter"]


@pytest.mark.parametrize("auto", [True, False])
def test_alarm_between_runs_shuts_down(make_rm, auto):
    rm = make_rm(auto=auto)                     # also in manual mode
    rm.alarm_handler([{"name": "rain"}])
    assert shutdown_started(rm)
    assert any("alarm ['rain']" in m for m in rm.messages)


def test_alarm_between_runs_when_off_does_nothing(make_rm):
    rm = make_rm(inverter=False)
    rm.alarm_handler([{"name": "rain"}])
    assert rm.runentry is None


def test_shutdown_not_blocked_by_alarms(make_rm):
    rm = make_rm()
    rm.hk = type("HK", (), {"get_alarm": lambda self: [{"name": "rain"}]})()
    assert rm.start_shutdown("test") is True
