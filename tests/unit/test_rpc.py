"""Baytech RPC dialogue: no busy wait, result read after the command was executed."""

import pytest

import lib.RPC as rpc_module
from lib.RPC import RPCOutlet, parse_status


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = 0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.sleeps += 1


class RPCSerial:
    """Baytech-like: Enter -> menu + prompt, 'on n' -> (Y/N)?, 'y' -> updated menu + prompt."""
    is_open = True

    def __init__(self, clock, menu_after_y=True, switch_delay=0.0, compact=True, silent=False):
        self.clock = clock
        self.state = {str(i): "Off" for i in range(1, 7)}
        self.out = []                 # (time, text)
        self.pending_cmd = None
        self.menu_after_y = menu_after_y
        self.switch_delay = switch_delay
        self.compact = compact
        self.silent = silent
        self.reads = 0

    def menu(self):
        dots = "..." if self.compact else " . . . "
        lines = [f"{i}){dots}OUTLET {i}    : {self.state[str(i)]}" for i in range(1, 7)]
        return "\r\n".join(["Circuit Breaker : On", ""] + lines + ["", "RPC>"])

    def emit(self, text, delay=0.0):
        if not self.silent:
            self.out.append((self.clock.t + delay, text))

    def write(self, data):
        text = data.decode().strip().lower()
        if text == "":
            self.emit(self.menu())
        elif text.startswith(("on ", "off ")):
            verb, n = text.split()
            self.pending_cmd = (verb, n)
            self.emit(f"Turn {verb.capitalize()} Outlet {n} (Y/N)?")
        elif text == "y" and self.pending_cmd:
            verb, n = self.pending_cmd
            self.state[n] = "On" if verb == "on" else "Off"
            self.emit(self.menu() if self.menu_after_y else f"Outlet {n} turned {verb}\r\nRPC>",
                      self.switch_delay)
            self.pending_cmd = None

    def flush(self):
        pass

    def read_all(self):
        self.reads += 1
        ready = [x for x in self.out if x[0] <= self.clock.t]
        self.out = [x for x in self.out if x[0] > self.clock.t]
        return "".join(t for _, t in ready).encode()

    def reset_input_buffer(self):
        self.out = [x for x in self.out if x[0] > self.clock.t]

    def reset_output_buffer(self):
        pass


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rpc_module, "_now", c.now)
    monkeypatch.setattr(rpc_module, "_sleep", c.sleep)
    return c


def outlet(clock, n=3, **kw):
    ser = RPCSerial(clock, **kw)
    return RPCOutlet(ser, n), ser


def test_on_off(clock):
    o, ser = outlet(clock)
    assert o.on() is True and ser.state["3"] == "On"
    assert o.status() is True
    assert o.off() is True and ser.state["3"] == "Off"


def test_result_read_after_switching(clock):
    # menu after Y comes 1.5 s later: the result must be the new state, not the old one
    o, _ = outlet(clock, switch_delay=1.5)
    assert o.on() is True


def test_rpc_without_menu_after_y(clock):
    o, _ = outlet(clock, menu_after_y=False)
    assert o.on() is True


def test_manual_style_dots(clock):
    o, _ = outlet(clock, compact=False)           # "3) . . . OUTLET 3 : Off" as in the manual
    assert o.status() is False and o.on() is True


def test_waiting_does_not_busy_loop(clock):
    o, ser = outlet(clock, switch_delay=2.0)
    o.on()
    # ~2 s of waiting at POLL_S = 0.05 s: tens of reads, not millions
    assert ser.reads < 200 and clock.sleeps > 0


def test_silent_rpc_keeps_waiting_and_warns(clock, monkeypatch):
    warnings = []
    monkeypatch.setattr(rpc_module, "_log", lambda level, msg: warnings.append(msg))
    o, ser = outlet(clock, silent=True)
    real_sleep = clock.sleep

    def sleep(s):
        real_sleep(s)
        if clock.t > 130:                          # stop the test after ~2 warnings
            raise KeyboardInterrupt
    monkeypatch.setattr(rpc_module, "_sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        o.status()
    assert len(warnings) == 2 and "still waiting for prompt" in warnings[0]


def test_parse_status():
    s = parse_status("1)...RAMAN    : On\r\n2) . . . radiometer : Off\r\nRPC>")
    assert s["1"] == {"device": "RAMAN", "state": "On"}
    assert s["2"]["state"] == "Off"
