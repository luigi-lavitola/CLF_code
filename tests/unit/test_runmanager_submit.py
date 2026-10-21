"""RunManager.submit: which job is started (if any) and what is recorded as 'in progress'."""

import datetime

import pytest

import lib.RunManager as rm_module
from lib.RunManager import RunManager
from lib.RunCalendar import RunEntry
from lib.Run import RunType


class FakeHK:
    def __init__(self, alarms=None):
        self.alarms = alarms or []

    def get_alarm(self):
        return self.alarms


class FakeProcess:
    started = []

    def __init__(self, target, args=()):
        self.target = target
        self.args = args
        self.alive = False

    def start(self):
        self.alive = True
        FakeProcess.started.append(self)

    def is_alive(self):
        return self.alive


def fake_run_class(tag):
    class FakeRun:
        def __init__(self, dc, params):
            self.tag = tag

        def execute(self, do_prepare=True, do_finish=True):
            pass
    return FakeRun


@pytest.fixture
def rm(monkeypatch):
    FakeProcess.started = []
    monkeypatch.setattr(rm_module.multiprocessing, "Process", FakeProcess)
    m = RunManager.__new__(RunManager)          # skip __init__: no calendar, no scheduler thread
    m.dc = None
    m.params = {}
    m.hk = FakeHK()
    m.runentry = None
    m.run = None
    m.job = None
    m.log = lambda *args, **kwargs: None
    m.RUN_CLASSES = {t: fake_run_class(t) for t in RunType}
    return m


def entry(runtype, last=False):
    return RunEntry(datetime.datetime.now(), runtype, False, last)


def test_alarm_does_not_restart_previous_run(rm):
    assert rm.submit(entry(RunType.FD), source="runmanager")
    previous_job, previous_run = rm.job, rm.run
    previous_job.alive = False                   # first run finished

    rm.hk.alarms = [{"name": "rain"}]
    assert rm.submit(entry(RunType.TANK), source="runmanager") is False

    assert len(FakeProcess.started) == 1        # nothing new started
    assert rm.job is previous_job and rm.run is previous_run


def test_alarm_on_first_run_does_not_crash(rm):
    rm.hk.alarms = [{"name": "rain"}]
    assert rm.submit(entry(RunType.FD), source="runmanager") is False
    assert FakeProcess.started == [] and rm.run is None


def test_busy_keeps_running_entry(rm):
    first = entry(RunType.RAMAN)
    assert rm.submit(first, source="runmanager")
    assert rm.submit(entry(RunType.FD), source="runmanager") is False
    assert rm.runentry is first                  # status/stop/kill still refer to the running job
    assert len(FakeProcess.started) == 1


@pytest.mark.parametrize("source,last,expected_args", [
    ("runmanager", False, (True, False)),        # keep instruments on between scheduled runs
    ("runmanager", True, ()),                    # last run of the night: full execute
    ("cli", False, ()),                          # manual run: always full execute
    ("cli", True, ()),
])
def test_execute_arguments(rm, source, last, expected_args):
    assert rm.submit(entry(RunType.FD, last=last), source=source)
    job = FakeProcess.started[-1]
    assert job.args == expected_args
    assert job.target.__self__ is rm.run


def test_run_class_matches_type(rm):
    for t in RunType:
        rm.job = None
        assert rm.submit(entry(t), source="cli")
        assert rm.run.tag is t


def test_rejects_non_entry(rm):
    with pytest.raises(TypeError):
        rm.submit("fd", source="cli")
