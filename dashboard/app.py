#!/usr/bin/env python3
"""
CLF/XLF shift dashboard: read-only web view of the logs.

    python3 dashboard/app.py [--logs DIR] [--port 8080] [--host 0.0.0.0]

The time range ("last N days") ends at the most recent data in the logs.
"""

import argparse
import collections
import os
import statistics

from flask import Flask, abort, jsonify, render_template, request

import logparse as lp

ROOT = lp.ROOT
app = Flask(__name__)
app.config["LOG_DIR"] = os.path.join(ROOT, "logs")

_runs_memo = {}


def _runs():
    """parse_runs() memoized on the state of the run.log files."""
    log_dir = app.config["LOG_DIR"]
    key = tuple((p, os.path.getsize(p), os.path.getmtime(p)) for p in lp._files(log_dir, "run.log"))
    if _runs_memo.get("key") != key:
        _runs_memo["key"] = key
        _runs_memo["value"] = lp.parse_runs(log_dir)
    return _runs_memo["value"]


def _site():
    try:
        import yaml
        with open(os.path.join(ROOT, "conf", "parameters.yml")) as f:
            params = {k: v for doc in yaml.safe_load_all(f) for k, v in doc.items()}
        return str(params.get("identity", "")).upper()
    except (OSError, ValueError, AttributeError):
        return ""


def _without_shots(run):
    return {k: v for k, v in run.items() if k != "shots"}


def _nights(runs, refusals):
    nights = collections.OrderedDict()
    for r in runs:
        n = nights.setdefault(lp.night_of(r["start"]), collections.Counter())
        n[r["type"]] += 1
        n["killed"] += r["status"] == "killed"
        n["error"] += r["status"] == "error"
        n["shots"] += r["n_shots"]
        n["packet"] += r["n_packet"]
        n["good"] += round(r["good_pct"] * r["n_shots"] / 100) if r["good_pct"] is not None else 0
    for f in refusals:
        nights.setdefault(lp.night_of(f["t"]), collections.Counter())["refused"] += 1
    out = []
    for night in sorted(nights, reverse=True):
        c = nights[night]
        out.append({"night": night, "FD": c["FD"], "TANK": c["TANK"], "CALIB": c["CALIB"], "RAMAN": c["RAMAN"],
                    "killed": c["killed"], "error": c["error"], "refused": c["refused"],
                    "packet_pct": 100.0 * c["packet"] / c["shots"] if c["shots"] else None,
                    "good_pct": 100.0 * c["good"] / c["shots"] if c["shots"] else None})
    return out


def _power_profile(runs, run_type):
    """Power of each shot relative to the median of its own run (%), median over the runs
    of one type by shot index: the warm-up shape, independent of the absolute energy."""
    by_index = collections.defaultdict(list)
    n_runs = 0
    for r in runs:
        if r["type"] != run_type or not r["power_median"]:
            continue
        n_runs += 1
        for s in r["shots"]:
            if s["power"] is not None and s["power"] >= 0:
                by_index[s["i"]].append(100.0 * s["power"] / r["power_median"])
    idx = sorted(by_index)
    return {"i": idx, "median": [statistics.median(by_index[i]) for i in idx], "n_runs": n_runs}


@app.route("/")
def index():
    return render_template("index.html", site=_site())


@app.route("/api/data")
def data():
    log_dir = app.config["LOG_DIR"]
    days = request.args.get("days", default=3, type=float)
    t_to = lp.latest_time(log_dir)
    t_from = 0.0 if days <= 0 else t_to - days * 86400
    runs_all, refusals_all, kills_all = _runs()
    runs = [r for r in runs_all if t_from <= r["start"] <= t_to]
    refusals = [f for f in refusals_all if t_from <= f["t"] <= t_to]
    events, all_events = lp.parse_events(log_dir, t_from, t_to)
    shots = sum(r["n_shots"] for r in runs)
    summary = {
        "runs": dict(collections.Counter(r["type"] for r in runs)),
        "shots": shots,
        "good_pct": (100.0 * sum(round((r["good_pct"] or 0) * r["n_shots"] / 100) for r in runs) / shots
                     if shots else None),
        "missing": sum(r["n_shots"] - r["n_packet"] for r in runs),
        "stale": sum(r["n_stale"] for r in runs),
        "wrong": sum(r["n_wrong"] for r in runs),
        "killed": sum(1 for r in runs if r["status"] == "killed"),
        "errors": sum(1 for e in all_events if e["level"] == "ERROR"),
        "refused": len(refusals),
    }
    return jsonify({
        "t_from": t_from if t_from else (runs_all[0]["start"] if runs_all else 0), "t_to": t_to,
        "summary": summary,
        "nights": _nights(runs, refusals),
        "runs": [_without_shots(r) for r in runs],
        "refusals": refusals,
        "kills": [k for k in kills_all if t_from <= k["t"] <= t_to],
        "profile": {t: _power_profile(runs, t) for t in ("FD", "TANK")},
        "hk": lp.parse_hk(log_dir, t_from or t_to - 365 * 86400, t_to),
        "events": events,
    })


@app.route("/api/run/<run_id>")
def run_detail(run_id):
    for r in _runs()[0]:
        if r["id"] == run_id:
            return jsonify(r)
    abort(404)


def main():
    ap = argparse.ArgumentParser(description="CLF/XLF shift dashboard (read only)")
    ap.add_argument("--logs", default=app.config["LOG_DIR"], help="log directory")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    app.config["LOG_DIR"] = os.path.abspath(args.logs)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
