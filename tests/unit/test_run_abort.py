"""Every run's abort() must stop the FPGA shot sequence before anything else."""

import pytest

import lib.Run as run_module
from lib.Run import RunFD, RunTank, RunCalib, RunRaman

from fakes import FakeDC

PARAMS = {"identity": "clf", "clf": {"tank_name": "celeste"}}


class FakeMotor:
    def move_ABS(self, pos):
        pass


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)


@pytest.mark.parametrize("run_class", [RunFD, RunTank, RunCalib, RunRaman])
def test_abort_disables_laser_first(run_class):
    dc = FakeDC(dio={"cover_raman_closed": True})
    dc.get_motor = lambda name: FakeMotor()
    run_class(dc, PARAMS).abort()
    assert dc.events[0] == ("dio", "laser_en", False)
