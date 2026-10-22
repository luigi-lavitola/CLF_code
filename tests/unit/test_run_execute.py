"""RunBase.execute(): a failed prepare/run always ends in a safe state."""

import pytest

import lib.Run as run_module
from lib.Run import RunBase, RunFD

from fakes import FakeDC

PARAMS = {"identity": "clf", "clf": {}}


class Probe(RunBase):
    def __init__(self, dc, prepare=0, run_raises=False):
        super().__init__(dc, PARAMS)
        self.calls = []
        self._prepare = prepare
        self._run_raises = run_raises

    def prepare(self):
        self.calls.append("prepare")
        if isinstance(self._prepare, Exception):
            raise self._prepare
        return self._prepare

    def run(self):
        self.calls.append("run")
        if self._run_raises:
            raise IOError("serial port gone")

    def finish(self):
        self.calls.append("finish")

    def abort(self):
        self.calls.append("abort")


def dc(inverter=True):
    return FakeDC(dio={"inverter": inverter})


@pytest.mark.parametrize("do_finish", [True, False])
def test_prepare_failure_aborts(do_finish):
    r = Probe(dc(), prepare=-1)
    r.execute(True, do_finish)
    assert r.calls == ["prepare", "abort"]


def test_prepare_exception_aborts():
    r = Probe(dc(), prepare=OSError("no answer"))
    r.execute(True, False)
    assert r.calls == ["prepare", "abort"]


@pytest.mark.parametrize("do_finish", [True, False])
def test_run_exception_aborts(do_finish):
    r = Probe(dc(), run_raises=True)
    r.execute(True, do_finish)
    assert r.calls == ["prepare", "run", "abort"]


def test_inverter_off_no_abort():
    # RPC unpowered: its blocking waits would never end; everything is already off
    r = Probe(dc(inverter=False), prepare=-1)
    r.execute(True, False)
    assert r.calls == ["prepare"]


def test_abort_exception_does_not_escape():
    r = Probe(dc(), prepare=-1)

    def bad_abort():
        raise IOError("RPC")
    r.abort = bad_abort
    r.execute(True, True)                            # must not raise


@pytest.mark.parametrize("do_finish,expected", [
    (True, ["prepare", "run", "finish"]),            # last run of the night
    (False, ["prepare", "run"]),                     # instruments kept on for the next run
])
def test_normal_paths_unchanged(do_finish, expected):
    r = Probe(dc())
    r.execute(True, do_finish)
    assert r.calls == expected


def test_fd_fire_refused_closes_vertical_cover(monkeypatch):
    # regression: the vertical cover is opened before fire(); a refused fire returned -1
    # from prepare and, on a non-last run, the cover stayed open
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(run_module.TimeSync, "ensure", lambda fpga, log: True)
    d = dc()
    d.laser.fire = lambda: -1
    run = RunFD(d, {"identity": "clf", "clf": {"fd_trigger_ms": 249.99411}})
    run.execute(True, False)
    assert ("outlet_on", "Vert_cover") in d.events
    assert d.outlets["Vert_cover"].state is False      # closed again by abort()
    assert d.events[-1] == ("dio", "inverter", False)
