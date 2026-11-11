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
