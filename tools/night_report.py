#!/usr/bin/env python3
"""
Morning report of the last observation night, sent to Telegram (one message per site).

    python3 tools/night_report.py                 # last finished night, send
    python3 tools/night_report.py --dry-run       # print the message only
    python3 tools/night_report.py --night 2026-11-11 --dry-run

Night D = 12:00 UTC of day D -> 12:00 UTC of D+1 (as in the dashboard). Checked:
  - runs expected from the FD calendar (docs/ALLFDCalendar.txt, run_list of the site)
    against the runs started in run.log: a stopped PC or main.py shows up as missing runs;
  - runs killed, with ERROR lines, without shots, or refused because of alarms;
  - valid shot timestamps per FD/TANK run;
  - ERROR / WARNING lines of run.log, device.log, hk.log;
  - logs that stop before the end of the night.

Telegram credentials: conf/telegram.yml (not in git)
    token: "123456789:AA..."      # from BotFather
    chat_id: 123456789            # user or group (negative) id
A message is sent every morning, also when all is fine: no message = something is down.
"""

import argparse
import collections
import datetime as dt
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
import logparse as lp                                   # noqa: E402

GOOD_PCT_MIN = 95.0         # FD/TANK run with fewer valid timestamps: problem
LOG_GAP_S = 1800            # logs ending this long before the end of the night: problem
MAX_LINES = 8               # per list in the message
TELEGRAM_MAX = 4000         # Telegram limit is 4096 characters
RUN_TYPES = ("FD", "TANK", "RAMAN", "CALIB")


def utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H:%M")


def night_window(night):
    """(t_from, t_to) in UNIX seconds of night 'YYYY-MM-DD'."""
    d = dt.datetime.strptime(night, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    t0 = (d + dt.timedelta(hours=12)).timestamp()
    return t0, t0 + 86400


def last_finished_night(now):
    return lp.night_of(now - 86400)


def load_yaml(path):
    import yaml
    with open(path) as f:
        out = {}
        for doc in yaml.safe_load_all(f):
            out.update(doc or {})
        return out


def expected_runs(params, t0, t1, calendar=os.path.join(ROOT, "docs", "ALLFDCalendar.txt")):
    """[(unix start, TYPE)] of the runs the calendar schedules in [t0, t1)."""
    from lib.RunCalendar import RunCalendar
    rc = RunCalendar(calendar, params)
    out = []
    for entry in rc.run_entries:
        for run in rc.get_timetable_for_entry(entry):
            t = run.start_time.replace(tzinfo=dt.timezone.utc).timestamp()   # calendar is in UTC
            if t0 <= t < t1:
                out.append((t, run.runtype.name))
    return sorted(out)


def _norm(msg):
    """Error message with the numbers blanked, to group repeated errors."""
    return re.sub(r"\d+(\.\d+)?", "#", msg)[:120]


def build_report(site, night, expected, runs, refusals, events, last_log_t, now):
    """(ok, text) of the report. expected [(t, TYPE)], runs/refusals/events as in logparse."""
    t0, t1 = night_window(night)
    problems = []

    exp = collections.Counter(t for _, t in expected)
    done = collections.Counter(r["type"].upper() for r in runs)
    refused = collections.Counter(f["type"].upper() for f in refusals)
    counts = ", ".join(f"{t} {done[t]}/{exp[t]}" for t in RUN_TYPES if exp[t] or done[t])
    for t in RUN_TYPES:
        missing = exp[t] - done[t] - refused[t]          # refused runs are listed on their own
        if missing > 0:
            problems.append(f"{missing} {t} run(s) never started ({done[t]} of {exp[t]} expected)")

    if not expected and not runs:
        counts = "no runs scheduled"

    for r in runs:
        if r["status"] != "ok":
            what = r["status"]
            if r["status"] == "error" and r.get("errors"):
                what += ": " + r["errors"][0][:100]
            problems.append(f"{r['type']} {utc(r['start'])} {what}")
    for f in refusals:
        why = ("alarms " + ", ".join(f["alarms"])) if f["reason"] == "alarm" else "another job running"
        problems.append(f"{f['type']} {utc(f['t'])} refused ({why})")

    ts_runs = [r for r in runs if r["type"].upper() in ("FD", "TANK") and r["n_shots"]]
    shots = sum(r["n_shots"] for r in ts_runs)
    good = sum(round((r["good_pct"] or 0) * r["n_shots"] / 100) for r in ts_runs)
    for r in ts_runs:
        if r["good_pct"] is not None and r["good_pct"] < GOOD_PCT_MIN:
            problems.append(f"{r['type']} {utc(r['start'])} valid timestamps {r['good_pct']:.0f} % "
                            f"({r['n_shots'] - r['n_packet']} without packet, "
                            f"{r['n_stale'] + r['n_wrong']} of another shot)")

    end = min(t1, now)
    if last_log_t < end - LOG_GAP_S:
        when = dt.datetime.fromtimestamp(last_log_t, dt.timezone.utc).strftime("%Y-%m-%d %H:%M") \
            if last_log_t else "never"
        problems.append(f"logs stop at {when} UTC: PC or main.py down?")

    levels = collections.Counter(e["level"] for e in events)
    errors = collections.Counter(_norm(e["msg"]) for e in events if e["level"] == "ERROR")

    ok = not problems and not levels["ERROR"]
    head = f"{'✅' if ok else '⚠️'} {site} night {night}: " + ("all OK" if ok else
                                                           f"{len(problems)} problem(s)" if problems
                                                           else f"{levels['ERROR']} ERROR line(s)")
    lines = [head, f"Runs (done/expected): {counts}"]
    if shots:
        lines.append(f"Valid timestamps: {100.0 * good / shots:.1f} % of {shots} shots")
    lines.append(f"Log lines: {levels['ERROR']} ERROR, {levels['WARNING']} WARNING")
    if problems:
        lines.append("")
        lines += ["• " + p for p in problems[:MAX_LINES]]
        if len(problems) > MAX_LINES:
            lines.append(f"• ... and {len(problems) - MAX_LINES} more")
    if errors:
        lines.append("")
        lines.append("Most frequent errors:")
        lines += [f"  {n}× {m}" for m, n in errors.most_common(3)]
    text = "\n".join(lines)
    return ok, text[:TELEGRAM_MAX]


def send_telegram(token, chat_id, text, retries=3):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, data=data, timeout=20) as resp:
                if resp.status == 200:
                    return
                err = f"HTTP {resp.status}"
        except OSError as e:          # URLError, HTTPError, timeouts
            err = str(e).replace(token, "<token>")
        print(f"telegram send attempt {attempt} failed: {err}", file=sys.stderr)
        time.sleep(10 * attempt)
    raise SystemExit("telegram: message not sent")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--night", help="YYYY-MM-DD (default: last finished night)")
    ap.add_argument("--logs", default=os.path.join(ROOT, "logs"))
    ap.add_argument("--params", default=os.path.join(ROOT, "conf", "parameters.yml"))
    ap.add_argument("--telegram", default=os.path.join(ROOT, "conf", "telegram.yml"))
    ap.add_argument("--identity", help="override identity of parameters.yml (clf/xlf)")
    ap.add_argument("--dry-run", action="store_true", help="print the message, do not send it")
    ap.add_argument("--only-problems", action="store_true", help="send nothing when all is OK")
    args = ap.parse_args()

    now = time.time()
    params = load_yaml(args.params)
    if args.identity:
        params["identity"] = args.identity
    identity = params["identity"]
    night = args.night or last_finished_night(now)
    t0, t1 = night_window(night)

    expected = expected_runs(params, t0, t1)
    runs_all, refusals_all, _ = lp.parse_runs(args.logs)
    runs = [r for r in runs_all if t0 <= r["start"] < t1]
    refusals = [f for f in refusals_all if t0 <= f["t"] < t1]
    _, events = lp.parse_events(args.logs, t0, t1)
    last_log_t = lp.latest_time(args.logs)

    ok, text = build_report(identity.upper(), night, expected, runs, refusals, events, last_log_t, now)
    sys.stdout.reconfigure(errors="replace")         # emoji on a non-UTF-8 console
    print(text)
    if args.dry_run or (ok and args.only_problems):
        return
    cfg = load_yaml(args.telegram)
    send_telegram(str(cfg["token"]), cfg["chat_id"], text)
    print("sent")


if __name__ == "__main__":
    main()
