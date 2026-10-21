"""RunManager scheduler and RunCalendar at the end of the calendar and on errors."""

import datetime
import threading
import time

import pytest

import lib.RunManager as rm_module
from lib.RunManager import RunManager
from lib.RunCalendar import RunCalendar, RunEntry
from lib.Run import RunType

PARAMS = {"identity": "clf",
          "clf": {"run_list": ["fd", "tank", "raman", "calib"], "start_minutes": [5, 20, 35, 50]}}

REAL_SLEEP = time.sleep


class FakeHK:
    def subscribe(self, f):
        pass

    def unsubscribe(self, f):
        pass

    def get_alarm(self):
        return []


def write_calendar(path, nights):
    """nights: list of (start, end) datetimes, all with FD shift."""
    lines = [f"1\t{s:%Y %m %d %H %M %S}   {e:%Y %m %d %H %M %S}" for s, e in nights]
    path.write_text("\n".join(lines) + "\n")


def test_calendar_exhausted_returns_empty(tmp_path):
    past = datetime.datetime.now() - datetime.timedelta(days=10)
    cal = tmp_path / "cal.txt"
    write_calendar(cal, [(past, past + datetime.timedelta(hours=6))])
    assert RunCalendar(str(cal), PARAMS).get_next_entries(dayoffset=1) == []


def test_timetable_empty_run_list():
    from lib.RunCalendar import CalendarEntry
    start = datetime.datetime(2026, 11, 1, 1, 0)
    rc = RunCalendar.__new__(RunCalendar)
    rc.params = {"identity": "clf", "clf": {"run_list": [], "start_minutes": [5, 20, 35, 50]}}
    rc.identity = "clf"
    assert rc.get_timetable_for_entry(CalendarEntry(start, start + datetime.timedelta(hours=5), True)) == []


def test_runmanager_starts_with_exhausted_calendar(tmp_path, monkeypatch):
    past = datetime.datetime.now() - datetime.timedelta(days=10)
    (tmp_path / "docs").mkdir()
    write_calendar(tmp_path / "docs" / "ALLFDCalendar.txt", [(past, past + datetime.timedelta(hours=6))])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rm_module.time, "sleep", lambda s: REAL_SLEEP(0.01))
    rm = RunManager(None, FakeHK(), PARAMS)
    REAL_SLEEP(0.1)
    assert rm.thr.is_alive()                         # scheduler did not crash on next_run() == None
    rm.close()


@pytest.fixture
def bare_rm(monkeypatch):
    monkeypatch.setattr(rm_module.time, "sleep", lambda s: REAL_SLEEP(0.01))
    m = RunManager.__new__(RunManager)
    m.loop = True
    m.scheduler_running = True
    m.log = lambda *args, **kwargs: None
    return m


def run_scheduler(m, seconds):
    t = threading.Thread(target=m.scheduler)
    t.start()
    REAL_SLEEP(seconds)
    alive = t.is_alive()
    m.loop = False
    t.join(2)
    return alive


def test_scheduler_runs_last_entry_then_idles(bare_rm):
    soon = datetime.datetime.now() + datetime.timedelta(milliseconds=100)
    bare_rm.runlist = [RunEntry(soon, RunType.MOCK, False, True)]
    submitted = []
    bare_rm.submit = lambda entry, source: submitted.append(entry.runtype)
    assert run_scheduler(bare_rm, 0.4)               # still alive after the list is empty
    assert submitted == [RunType.MOCK] and bare_rm.runlist == []


def test_scheduler_survives_submit_exception(bare_rm):
    now = datetime.datetime.now()
    bare_rm.runlist = [RunEntry(now + datetime.timedelta(milliseconds=100), RunType.FD),
                       RunEntry(now + datetime.timedelta(milliseconds=250), RunType.TANK)]
    submitted = []

    def submit(entry, source):
        submitted.append(entry.runtype)
        if entry.runtype == RunType.FD:
            raise OSError("serial port gone")
    bare_rm.submit = submit
    assert run_scheduler(bare_rm, 0.6)
    assert submitted == [RunType.FD, RunType.TANK]   # the next run is still scheduled
