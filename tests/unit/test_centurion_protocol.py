"""Centurion serial protocol: acknowledgement packets read correctly and matched to their command."""

import pytest

import lib.Centurion as cent_module
from lib.Centurion import Centurion


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class LaserSerial:
    """Byte-level laser: answers each command with a packet after `delay` seconds."""
    is_open = True
    port = None

    def __init__(self, clock):
        self.clock = clock
        self.timeout = 2
        self.incoming = []            # (arrival time, byte)
        self.answers = {}             # command name -> (answer bytes, delay)
        self.written = []

    def answer(self, name, text, delay=0.05, terminator=b"\r\n"):
        self.answers[name] = (text.encode("latin-1") + terminator, delay)

    def push(self, data, at):
        self.incoming += [(at, bytes([b])) for b in data]
        self.incoming.sort(key=lambda x: x[0])

    def write(self, data):
        cmd = data.decode().strip()
        self.written.append(cmd)
        key = cmd.split()[0]
        if key in self.answers:
            text, delay = self.answers[key]
            self.push(text, self.clock.t + delay)

    def read(self, n):
        assert n == 1
        if self.incoming and self.incoming[0][0] <= self.clock.t + self.timeout:
            at, b = self.incoming.pop(0)
            self.clock.t = max(self.clock.t, at)
            return b
        self.clock.t += self.timeout
        return b""

    def reset_input_buffer(self):
        self.incoming = [x for x in self.incoming if x[0] > self.clock.t]

    def reset_output_buffer(self):
        pass


@pytest.fixture
def laser(monkeypatch):
    clock = Clock()
    ser = LaserSerial(clock)
    monkeypatch.setattr(cent_module.serial, "Serial", lambda **kw: ser)
    monkeypatch.setattr(cent_module, "_now", clock.now)
    monkeypatch.setattr(cent_module, "_sleep", clock.sleep)
    monkeypatch.setattr(cent_module.time, "sleep", clock.sleep)      # flush_buffers
    c = Centurion("/dev/null")
    c.clock, c.ser = clock, ser
    return c


def test_answer_returned_as_soon_as_complete(laser):
    laser.ser.answer("$STATUS", "$STATUS 7E 00 00 00 00")
    t0 = laser.clock.t
    assert laser.send_command("$STATUS ?") == "$STATUS 7E 00 00 00 00"
    assert laser.clock.t - t0 < 0.5             # old code: always waited the 2 s serial timeout


def test_late_answer_within_5s_is_not_lost(laser):
    laser.ser.answer("$TEMPS", "$TEMPS 300 200 210", delay=3.5)
    assert laser.send_command("$TEMPS ?") == "$TEMPS 300 200 210"


def test_late_answer_of_previous_command_is_ignored(laser):
    # the $DIODE answer is late and arrives while waiting for $QSON
    laser.ser.answer("$DIODE", "$DIODE 1", delay=6.0)
    laser.ser.answer("$QSON", "$QSON 1", delay=0.5)
    assert laser.send_command("$DIODE 1") == ""          # timeout for $DIODE
    laser.ser.push(b"$DIODE 1\r\n", laser.clock.t + 0.1)  # ...and now its answer shows up
    assert laser.send_command("$QSON 1") == "$QSON 1"


@pytest.mark.parametrize("bad", ["$Bad Command", "$Bad Value"])
def test_bad_answers_are_errors(laser, bad):
    laser.ser.answer("$DPW", bad)
    assert laser.send_command("$DPW 999") == ""
    assert laser.set_parameter("$DPW", 999) == -1


def test_noise_byte_does_not_raise(laser):
    laser.ser.answer("$STATUS", "$STATUS 7E 00\xff 00 00 00")
    laser.send_command("$STATUS ?")              # old code: UnicodeDecodeError


@pytest.mark.parametrize("terminator", [b"\r", b"\n", b"\r\n"])
def test_terminators(laser, terminator):
    laser.ser.answer("$QSON", "$QSON 1", terminator=terminator)
    laser.ser.answer("$DIODE", "$DIODE 1", terminator=terminator)
    assert laser.send_command("$QSON 1") == "$QSON 1"
    assert laser.send_command("$DIODE 1") == "$DIODE 1"


def test_no_answer(laser):
    assert laser.send_command("$STATUS ?") == ""
    assert laser.status() is None


def test_set_parameter_ok(laser):
    laser.ser.answer("$DFREQ", "$DFREQ 100")
    assert laser.set_parameter("$DFREQ", 100) == 0


def test_set_mode_fails_if_never_ready(laser):
    for name, val in [("$DFREQ", 100), ("$DIODE", 1), ("$QSON", 1), ("$QSWIT", 1),
                      ("$DTRIG", 1), ("$QSTRI", 1), ("$DPW", 140), ("$QSDEL", 145)]:
        laser.ser.answer(name, f"{name} {val}")
    laser.ser.answer("$STANDBY", "$STANDBY")
    laser.ser.answer("$STATUS", "$STATUS 3E 00 00 00 00")      # never 0x7E
    assert laser.set_mode(qson=1, dpw=140) == -1


def test_fire_not_acknowledged(laser):
    laser.ser.answer("$STATUS", "$STATUS 7E 00 00 00 00")
    laser.ser.answer("$TEMPS", "$TEMPS 300 200 200")
    laser.ser.answer("$FIRE", "$Bad Command")
    assert laser.fire() == -3


def test_fire_acknowledged(laser):
    laser.ser.answer("$STATUS", "$STATUS 7E 00 00 00 00")
    laser.ser.answer("$TEMPS", "$TEMPS 300 200 200")
    laser.ser.answer("$FIRE", "$FIRE")
    assert laser.fire() == 0
    assert "$FIRE" in laser.ser.written
