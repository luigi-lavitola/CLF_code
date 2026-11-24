"""tools/gps_fixed_position.py: ECEF conversion, CFG-TMODE2 payload, average of hk.log."""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import gps_fixed_position as g                                  # noqa: E402


def test_ecef_matches_the_bench_position():
    # set on the bench LEA-M8F on 2026-11-04 (u-blox accepted it: fixType 5)
    x, y, z = g.lla_to_ecef(40.8379965, 14.1828290, 191.4)
    assert (x, y, z) == pytest.approx((4685218.81, 1184048.71, 4148953.83), abs=0.05)


def test_tmode2_payload():
    p = g.tmode2_payload(2, (4685218.81, 1184048.71, 4148953.83), 2000)
    assert len(p) == 28
    assert struct.unpack("<BBHiiiIII", p) == (2, 0, 0, 468521881, 118404871, 414895383, 2000, 0, 0)
    assert g.ubx_c_arg(g.tmode2_payload(0)) == "0x06,0x3d," + ",".join(["0x00"] * 28)


def test_average_uses_only_good_samples(tmp_path):
    lines = []
    for i in range(400):
        lat = 40.0 + (1e-6 if i % 2 else -1e-6)
        lines.append(f"2026-11-25 0{i // 360}:{(i // 6) % 60:02d}:{(i % 6) * 10:02d},000 - housekeeping - INFO -  "
                     f"gps_fix=True[] gps_holdover=0[] gps_sats_used=12[] gps_lat={lat}[deg] gps_lon=14.0[deg] gps_alt=200.0[m]")
    lines.append("2026-11-25 01:30:00,000 - housekeeping - INFO -  gps_fix=False[] gps_holdover=0[] "
                 "gps_sats_used=12[] gps_lat=41.0[deg] gps_lon=15.0[deg] gps_alt=900.0[m]")
    lines.append("2026-11-25 01:30:10,000 - housekeeping - INFO -  gps_fix=True[] gps_holdover=1[] "
                 "gps_sats_used=12[] gps_lat=41.0[deg] gps_lon=15.0[deg] gps_alt=900.0[m]")
    (tmp_path / "hk.log").write_text("\n".join(lines) + "\n")
    t0 = g.lp._epoch("2026-11-25 00:00:00", "0")
    avg = g.average(str(tmp_path), t0, t0 + 86400)
    assert avg["n"] == 400
    assert (avg["lat"], avg["lon"], avg["alt"]) == pytest.approx((40.0, 14.0, 200.0), abs=2e-6)
    assert avg["std_n"] == pytest.approx(0.111, abs=0.01)
