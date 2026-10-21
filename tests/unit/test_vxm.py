"""VXM motor controller: ready prompt, status queries, command results (Velmex VXM manual)."""

import pytest

import lib.VXM as vxm_module
from lib.VXM import VXM


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class VXMSerial:
    """Answers 'R' (run) with `run_reply` after the move, 'V' with `status`."""
    is_open = True
    port = None
    baudrate = 9600

    def __init__(self, clock, run_reply=b"^", status=b"R", move_s=1.0):
        self.clock = clock
        self.run_reply = run_reply
        self.status = status
        self.move_s = move_s
        self.pending = []           # (time, bytes)
        self.written = []
        self.timeout = 0.2

    def write(self, data):
        self.written.append(data)
        if data == b"R\r" and self.run_reply is not None:
            self.pending.append((self.clock.t + self.move_s, self.run_reply))
        elif data == b"V":
            self.pending.append((self.clock.t, self.status))

    def read(self, n):
        ready = [p for p in self.pending if p[0] <= self.clock.t]
        if not ready:
            self.clock.t += self.timeout
            return b""
        self.pending = [p for p in self.pending if p[0] > self.clock.t]
        data = b"".join(d for _, d in ready)
        return data[:n]

    def reset_input_buffer(self):
        self.pending = [p for p in self.pending if p[0] > self.clock.t]

    def reset_output_buffer(self):
        pass


@pytest.fixture
def make_motor(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(vxm_module.time, "sleep", clock.sleep)
    monkeypatch.setattr(vxm_module.time, "monotonic", clock.now)

    def make(**kw):
        ser = VXMSerial(clock, **kw)
        motor = VXM.Motor(ser, 1, 0, 0)
        motor.log = lambda *a, **k: None
        return motor, ser
    return make


def test_move_completes(make_motor):
    m, ser = make_motor()
    assert m.move_ABS(1000) == 0
    assert b"IA1M1000\r" in ser.written


def test_prompt_with_extra_characters(make_motor):
    # old code: response "^^" (or with other chars) never equal to "^": endless loop
    m, _ = make_motor(run_reply=b"^^")
    assert m.move_ABS(1000) == 0


def test_motor_never_done_times_out_and_kills(make_motor):
    m, ser = make_motor(run_reply=None)
    assert m.move_ABS(1000) == -1
    assert b"K" in ser.written


def test_failed_move_is_reported(make_motor):
    m, _ = make_motor(run_reply=None)
    assert m.move_Neg0() == -1 and m.set_ABSzero() == -1 and m.move_BWD(10) == -1


def test_status_query(make_motor):
    m, _ = make_motor(status=b"R")
    assert m.query("V") == "R"


@pytest.mark.parametrize("status,expected", [(b"R", 0), (b"B", -1)])
def test_set_acc_uses_status_query(make_motor, status, expected):
    # old code: called clear(), which did not exist (AttributeError), and compared 0/-1 with "R"
    m, _ = make_motor(status=status)
    assert m.set_acc(2000) == expected
