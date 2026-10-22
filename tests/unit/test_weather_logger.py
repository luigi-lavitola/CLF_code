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
