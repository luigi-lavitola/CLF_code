"""Centurion.fire(): $FIRE only after a successful, in-range temperature readout."""

import types

import pytest

import lib.Centurion as cent_module
from lib.Centurion import Centurion


class FakeSerial:
    is_open = True
    port = None

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass


@pytest.fixture
def make_laser(monkeypatch):
    monkeypatch.setattr(cent_module.serial, "Serial", lambda **kw: FakeSerial())
    monkeypatch.setattr(cent_module.time, "sleep", lambda s: None)

    def make(temps_replies):
        laser = Centurion("/dev/null")
        replies = iter(temps_replies)
        sent = []

        def send_command(cmd):
            sent.append(cmd)
            if cmd == "$TEMPS ?":
                return next(replies)
            if cmd == "$STATUS ?":
                return "$STATUS 7E 00 00 00 00"
            return cmd
        laser.send_command = send_command
        return laser, sent
    return make


@pytest.mark.parametrize("reply", ["", "garbage", "$TEMPS 40 x 30", "$TEMPS 40 30"])
def test_failed_readout_does_not_fire(make_laser, reply):
    laser, sent = make_laser([reply])
    assert laser.fire() != 0
    assert "$FIRE" not in sent


def test_stale_good_readout_is_not_reused(make_laser):
    laser, sent = make_laser(["$TEMPS 300 200 200", ""])
    assert laser.fire() == 0                     # first: good readout, fires
    sent.clear()
    assert laser.fire() != 0                     # second: readout fails, old values must not count
    assert "$FIRE" not in sent


def test_out_of_range_does_not_fire(make_laser):
    laser, sent = make_laser(["$TEMPS 510 200 200"])
    assert laser.fire() == -2
    assert "$FIRE" not in sent


def test_in_range_fires(make_laser):
    laser, sent = make_laser(["$TEMPS 500 450 450"])
    assert laser.fire() == 0
    assert sent[-1] == "$FIRE"
