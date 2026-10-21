"""RunRaman: the cover-close part of run() and abort() must complete the shutdown even on timeout."""

import pytest

import lib.Run as run_module
from lib.Run import RunRaman

from fakes import FakeDC

PARAMS = {"identity": "clf", "clf": {}}


class FakeStream:
    def __init__(self, text=""):
        self.text = text

    def read(self):
        return self.text.encode()


class FakeSSH:
    def set_missing_host_key_policy(self, policy):
        pass

    def connect(self, *args, **kwargs):
        pass

    def exec_command(self, cmd):
        out = "1234" if cmd.startswith("./start12") else ""     # pid, then "process ended"
        return FakeStream(), FakeStream(out), FakeStream()

    def close(self):
        pass


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(run_module.paramiko, "SSHClient", FakeSSH)


def make_run(dio):
    dc = FakeDC(dio=dio, registers={"shots_cnt": 75000})
    r = RunRaman(dc, PARAMS)
    return r, dc


STUCK = {"cover_raman_open": False, "cover_raman_closed": False}     # cover never reaches a limit switch
CLOSED = {"cover_raman_open": False, "cover_raman_closed": True}


@pytest.mark.parametrize("dio", [STUCK, CLOSED])
def test_run_turns_off_raman_daq(dio):
    r, dc = make_run(dio)
    r.run()
    assert ("outlet_off", "RAMAN_cover") in dc.events
    assert dc.events[-1] == ("outlet_off", "RAMAN_inst")


@pytest.mark.parametrize("dio", [STUCK, CLOSED])
def test_abort_completes_shutdown(dio):
    r, dc = make_run(dio)
    r.abort()
    ev = dc.events
    assert ("dio", "flipper_raman", False) in ev
    for outlet in ("radiometer", "laser", "VXM"):              # finish()
        assert ("outlet_off", outlet) in ev
    assert ev[-1] == ("dio", "inverter", False)


def test_close_cover_wait_result():
    assert make_run(CLOSED)[0].close_cover_wait() is True
    assert make_run(STUCK)[0].close_cover_wait() is False
    still_open = {"cover_raman_open": True, "cover_raman_closed": False}
    assert make_run(still_open)[0].close_cover_wait() is False
