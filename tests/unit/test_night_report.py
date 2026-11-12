"""tools/night_report.py: message built from the parsed logs and the calendar."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import night_report as nr                                    # noqa: E402

NIGHT = "2026-11-11"
T0, T1 = nr.night_window(NIGHT)          # 2026-11-11 12:00 -> 2026-11-12 12:00 UTC
NOW = T1 + 300


def run(rtype, t, status="ok", n=50, good=100.0, packet=None, errors=()):
    return {"type": rtype, "start": t, "status": status, "n_shots": n, "good_pct": good,
            "n_packet": n if packet is None else packet, "n_stale": 0, "n_wrong": 0,
            "errors": list(errors)}


def expected(*types):
    return [(T0 + 3600 * (i + 1), t) for i, t in enumerate(types)]


def report(exp, runs, refusals=(), events=(), last_log=NOW - 60):
    return nr.build_report("CLF", NIGHT, exp, list(runs), list(refusals), list(events), last_log, NOW)


def test_night_window_and_default_night():
    assert T1 - T0 == 86400
    assert nr.last_finished_night(T1 + 300) == NIGHT          # 12:05 UTC -> the night just ended


def test_all_ok():
    ok, text = report(expected("FD", "FD", "TANK"),
                      [run("FD", T0 + 3600), run("FD", T0 + 7200), run("TANK", T0 + 10800, n=3)])
    assert ok
    assert text.startswith("✅ CLF night 2026-11-11: all OK")
    assert "FD 2/2, TANK 1/1" in text and "100.0 % of 103 shots" in text


def test_no_runs_scheduled_is_ok():
    ok, text = report([], [])
    assert ok and "no runs scheduled" in text


def test_missing_killed_error_and_bad_timestamps():
    ok, text = report(expected("FD", "FD", "FD", "CALIB"),
                      [run("FD", T0 + 3600, status="killed"),
                       run("FD", T0 + 7200, good=60.0, packet=30),
                       run("CALIB", T0 + 14400, status="error", errors=["laser not ready"])])
    assert not ok
    assert "1 FD run(s) never started (2 of 3 expected)" in text
    assert "killed" in text and "error: laser not ready" in text
    assert "valid timestamps 60 % (20 without packet" in text


def test_refused_run_not_counted_as_missing():
    refusal = {"t": T0 + 3600, "type": "FD", "reason": "alarm", "alarms": ["rain"]}
    ok, text = report(expected("FD"), [], refusals=[refusal])
    assert not ok
    assert "refused (alarms rain)" in text and "never started" not in text


def test_logs_stopped():
    ok, text = report(expected("FD"), [run("FD", T0 + 3600)], last_log=T0 + 4000)
    assert not ok and "logs stop at" in text


def test_error_lines_make_it_not_ok_and_are_grouped():
    ev = [{"level": "ERROR", "msg": f"shot {i}: no timestamp packet within 2.5s"} for i in (3, 7)]
    ev.append({"level": "WARNING", "msg": "x"})
    ok, text = report(expected("FD"), [run("FD", T0 + 3600)], events=ev)
    assert not ok and "2 ERROR line(s)" in text and "1 WARNING" in text
    assert "2× shot #: no timestamp packet within #s" in text


def test_long_lists_are_cut():
    runs = [run("FD", T0 + 60 * i, status="killed") for i in range(20)]
    ok, text = report(expected(*["FD"] * 20), runs)
    assert "... and 12 more" in text and len(text) <= nr.TELEGRAM_MAX


def hk_row(t, fix=True, holdover=0.0, tacc=8.0, lock=None):
    v = {"gps_fix": (1.0 if fix else 0.0, "", True), "gps_holdover": (holdover, "", False),
         "gps_tacc_ns": (tacc, "ns", False)}
    if lock is not None:
        v["fpga_lock_lost"] = (lock, "", False)
    return (t, v)


def test_gps_loss_and_lock_lost_are_problems():
    rows = [hk_row(T0 + 10 * i, lock=0) for i in range(100)]
    rows += [hk_row(T0 + 1000 + 10 * i, fix=False, holdover=1.0, tacc=None) for i in range(60)]
    rows += [hk_row(T0 + 1600, lock=1), hk_row(T0 + 1610, lock=0)]
    ok, text = report(expected("FD"), [run("FD", T0 + 3600)])
    assert ok and "GPS:" not in text                      # not checked without hk rows
    ok, text = nr.build_report("CLF", NIGHT, expected("FD"), [run("FD", T0 + 3600)], [], [], NOW - 60,
                               NOW, nr.time_ref_summary(rows))
    assert not ok
    assert "GPS without fix or in holdover 10 min (12:16 for 10 min)" in text
    assert "FPGA clock (MMCM) lost lock 1× from 12:26" in text
    assert "tAcc max 8 ns" in text


def test_gps_ok_line():
    rows = [hk_row(T0 + 10 * i, lock=0) for i in range(100)]
    rows.append(hk_row(T0 + 1000, fix=False))            # one sample: below GPS_BAD_MIN_S
    ok, text = nr.build_report("CLF", NIGHT, [], [], [], [], NOW - 60, NOW, nr.time_ref_summary(rows))
    assert ok and "GPS: fix and locked 100.0 % of the night, tAcc max 8 ns; FPGA clock always locked" in text
