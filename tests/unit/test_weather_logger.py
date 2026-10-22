"""Weather station record parsing (tools/weather_logger.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import weather_logger as wl                                    # noqa: E402

# 12 fields: code, year, day, hhmm, T, RH, wind cur/avg/max, two more, pressure (last)
WARM = "01+0105. 02+2026. 03+0295. 04+1435. 05+0012.34 06+0045.2 07+0003.1 08+0002.4 09+0007.8 10+0000.0 11+0000.0 12+0850.3"


def test_parse_record():
    r = wl.to_record(wl.parse_fields(WARM))
    assert (r["code"], r["year"], r["day"], r["hour"], r["minute"]) == (105, 2026, 295, 14, 35)
    assert r["temperature"] == 12.34 and r["humidity"] == 45.2
    assert (r["curwspeed"], r["avgwspeed"], r["maxwspeed"]) == (3.1, 2.4, 7.8)
    assert r["pressure"] == 850.3


def test_negative_temperature():
    # old spike: m.split('+')[1] -> IndexError, the whole reading was lost below 0 C
    cold = WARM.replace("05+0012.34", "05-0007.5")
    assert wl.to_record(wl.parse_fields(cold))["temperature"] == -7.5


def test_midnight_hhmm():
    r = wl.to_record(wl.parse_fields(WARM.replace("04+1435.", "04+0005.")))
    assert (r["hour"], r["minute"]) == (0, 5)


@pytest.mark.parametrize("raw", ["", "01+0105. 02+2026.", WARM.replace("06+0045.2", "06+00?5.2"),
                                 WARM.replace("07+0003.1", "07+")])
def test_bad_records_raise(raw):
    with pytest.raises(ValueError):
        wl.parse_fields(raw)


# --- service loop: MOXA off with the inverter -------------------------------------------

@pytest.fixture
def station(monkeypatch, tmp_path):
    """Replays answers: str = raw record, '' = no answer, Exception = port not available."""
    answers = []
    messages = []
    rows = []

    def read_station(**kw):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(wl, "read_station", read_station)
    monkeypatch.setattr(wl, "sleep_to_next", lambda s: None)
    monkeypatch.setattr(wl, "save_csv", lambda record, when: rows.append(record))
    monkeypatch.setattr(wl.log, "info", lambda msg, *a: messages.append(("info", msg % a if a else msg)))
    monkeypatch.setattr(wl.log, "error", lambda msg, *a: messages.append(("error", msg % a if a else msg)))
    monkeypatch.setattr(wl.log, "warning", lambda msg, *a: messages.append(("warning", msg % a if a else msg)))

    def run(seq):
        answers[:] = seq
        wl.loop({"port": "x"}, 300, cycles=len(seq))
        return messages, rows
    return run


def test_moxa_off_logged_once_not_every_reading(station):
    off = wl.serial.SerialException("port not available")
    messages, rows = station([WARM, "", off, "", "", WARM])
    not_answering = [m for m in messages if "not answering" in m[1]]
    again = [m for m in messages if "answering again" in m[1]]
    assert len(not_answering) == 1 and len(again) == 1
    assert not any(level == "error" for level, _ in messages)
    assert len(rows) == 2


def test_garbage_answer_is_an_error_each_time(station):
    messages, rows = station(["01+0105. garbage", "01+0105. garbage"])
    assert [level for level, _ in messages if level == "error"] == ["error", "error"]
    assert rows == []
