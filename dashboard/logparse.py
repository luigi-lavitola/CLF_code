"""
Read-only parsing of the CLF/XLF logs for the dashboard.

  run.log*     runs (submit / prepare steps / shots / errors), refusals, kills
  hk.log*      housekeeping, one line every ~10 s: "name=value[unit] ..." (self-describing)
  device.log*  device dialogue (only WARNING / ERROR are used)

Both log formats are understood:
  old  "... seconds: <unix>, counter: <buggy or ns> ..." (counter recovered when needed)
  new  "... gps_seconds: <gps>, counter: <ns> ..."
Files are parsed once and cached by (size, mtime): rotated files never change.
"""

import datetime as dt
import glob
import math
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
from recover_timestamps import candidates, choose, KNOWN_PPS_DELAYS, PULSE_ENERGY   # noqa: E402
from lib.GpsTime import gps_to_unix, unix_to_gps                                      # noqa: E402

NOMINALS = [d + PULSE_ENERGY for d in KNOWN_PPS_DELAYS]

LINE_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}) - (\w+)::(\w+) - (\w+) - (.*)$")
HK_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}) - housekeeping - (\w+) - (.*)$")
HK_FIELD_RE = re.compile(r"(\w+)=([^\[\s]*)\[([^\]]*)\]")
SHOT_RE = re.compile(r"^power (\d+) shot:\s*(\S*), (gps_seconds|seconds): (\d+), counter: ([-\d.eE+]+), "
                     r"pps distance: (-?[\d.eE+]+)ns, counter cycle: (\d+)")
SUBMIT_RE = re.compile(r"^start (\w+) run$")
REFUSE_RE = re.compile(r"^(\w+) run cannot start due to (alarms|other job running)")
ALARM_NAME_RE = re.compile(r"'name': '(\w+)'")
KILL_RE = re.compile(r"^(\w+) run killed")

STEP_DURATIONS = {"laser setup": "laser_setup_s",
                  "laser warmup and wait for laser fire auth": "fire_auth_s"}

STALE_S = 5            # packet seconds this far from the log time: packet of an earlier shot
INVALID_HK = 1e5       # e.g. LTC2983 faulted channel read as 4193305 C by the old code


def _epoch(date_s, ms):
    return dt.datetime.strptime(date_s, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=dt.timezone.utc).timestamp() + int(ms) / 1000


def _float(text):
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


# ---------------------------------------------------------------- file cache

_cache = {}


def _cached(path, parser):
    st = os.stat(path)
    key = (path, parser.__name__)
    hit = _cache.get(key)
    if hit and hit[0] == (st.st_size, st.st_mtime):
        return hit[1]
    data = parser(path)
    _cache[key] = ((st.st_size, st.st_mtime), data)
    return data


def _files(log_dir, base):
    """Rotated files (base.YYYY-MM-DD) in date order, then the current one."""
    rotated = sorted(glob.glob(os.path.join(log_dir, base + ".*")))
    current = os.path.join(log_dir, base)
    return rotated + ([current] if os.path.isfile(current) else [])


# ---------------------------------------------------------------- run.log

def _parse_run_file(path):
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE_RE.match(line.rstrip("\n"))
            if m:
                d, ms, cls, func, level, msg = m.groups()
                out.append((_epoch(d, ms), cls, func, level, msg))
    return out


def _shot(msg, t):
    m = SHOT_RE.match(msg)
    if not m:
        return None
    i, power, kind, sec, counter, pps, cyc = m.groups()
    sec, counter, pps, cyc = int(sec), float(counter), float(pps), int(cyc)
    s = {"i": int(i), "t": t, "power": _float(power), "cycle": cyc, "pps_ns": pps,
         "packet": sec > 0}
    if not s["packet"]:
        return s
    unix = gps_to_unix(sec) if kind == "gps_seconds" else sec
    s["unix"] = unix
    s["stale"] = abs(unix - t) > STALE_S
    s["wrong"] = (not s["stale"]) and cyc != s["i"] + 1
    if kind == "gps_seconds" or counter > 1.1e8:
        t_local_ns = counter                         # parser already fixed: ns
    else:
        c = candidates(int(counter))                 # old parser: recover the tick
        t_local_ns = choose(c, NOMINALS)[0] * 10.0 if c else None
    s["t_gps_ns"] = None if t_local_ns is None else t_local_ns - (pps - 10.0)
    return s


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _summarise(run):
    shots = run.pop("_shots")
    good = [s for s in shots if s["packet"] and not s["stale"] and not s["wrong"]]
    n = len(shots)
    run.update({
        "n_shots": n,
        "n_packet": sum(1 for s in shots if s["packet"]),
        "n_stale": sum(1 for s in shots if s["packet"] and s["stale"]),
        "n_wrong": sum(1 for s in shots if s["packet"] and s["wrong"]),
        "n_power_bad": sum(1 for s in shots if s["power"] is None or s["power"] < 0),
        "power_median": _median([s["power"] for s in shots if s["power"] is not None and s["power"] >= 0]),
        "t_gps_ms": None, "t_spread_ns": None, "drift_ns_per_shot": None,
        "pps_median_ns": _median([s["pps_ns"] for s in good]),
    })
    run["packet_pct"] = 100.0 * run["n_packet"] / n if n else None
    run["good_pct"] = 100.0 * len(good) / n if n else None
    tg = [(s["i"], s["t_gps_ns"]) for s in good if s["t_gps_ns"] is not None]
    if tg:
        vals = [v for _, v in tg]
        run["t_gps_ms"] = statistics.median(vals) / 1e6
        run["t_spread_ns"] = max(vals) - min(vals)
        if len(tg) >= 3:
            xs, ys = zip(*tg)
            mx, my = statistics.mean(xs), statistics.mean(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            run["drift_ns_per_shot"] = sum((x - mx) * (y - my) for x, y in tg) / sxx if sxx else None
    run["shots"] = shots
    return run


def parse_runs(log_dir):
    """(runs, refusals, kills) over all run.log files, in time order."""
    lines = []
    for path in _files(log_dir, "run.log"):
        lines.extend(_cached(path, _parse_run_file))
    lines.sort(key=lambda x: x[0])

    runs, refusals, kills = [], [], []
    cur, pending_step = None, None
    for t, cls, func, level, msg in lines:
        if cls == "RunManager":
            m = SUBMIT_RE.match(msg)
            if m:
                if cur:
                    runs.append(_summarise(cur))
                cur = {"id": f"{m.group(1)}-{int(t)}", "type": m.group(1), "start": t, "end": t,
                       "prepare_s": None, "laser_setup_s": None, "fire_auth_s": None,
                       "errors": [], "killed": False, "_shots": []}
                pending_step = None
                continue
            m = REFUSE_RE.match(msg)
            if m:
                refusals.append({"t": t, "type": m.group(1),
                                 "reason": "alarm" if m.group(2) == "alarms" else "busy",
                                 "alarms": sorted(set(ALARM_NAME_RE.findall(msg)))})
                continue
            m = KILL_RE.match(msg)
            if m:
                kills.append({"t": t, "type": m.group(1)})
                if cur and cur["type"] == m.group(1):
                    cur["killed"] = True
                continue
            continue
        if cur is None or not cls.startswith("Run"):
            continue
        cur["end"] = t
        if level == "ERROR":
            cur["errors"].append(msg)
        if msg.startswith("start ") and " Run" in msg and cur["prepare_s"] is None:
            cur["prepare_s"] = t - cur["start"]
        if msg in STEP_DURATIONS:
            pending_step = (STEP_DURATIONS[msg], t)
        elif msg == "done" and pending_step:
            cur[pending_step[0]] = t - pending_step[1]
            pending_step = None
        if func == "run":
            s = _shot(msg, t)
            if s:
                cur["_shots"].append(s)
    if cur:
        runs.append(_summarise(cur))
    for r in runs:
        r["status"] = ("killed" if r["killed"] else "error" if r["errors"]
                       else "no shots" if r["type"] in ("FD", "TANK", "CALIB") and not r["n_shots"]
                       else "ok")
    return runs, refusals, kills


# ---------------------------------------------------------------- hk.log

def _parse_hk_file(path):
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HK_RE.match(line.rstrip("\n"))
            if not m or m.group(3) != "INFO":
                continue
            d, ms, _, body = m.groups()
            values = {}
            for name, value, unit in HK_FIELD_RE.findall(body):
                if value in ("True", "False"):
                    values[name] = (1.0 if value == "True" else 0.0, unit, True)
                else:
                    v = _float(value)
                    if v is not None and abs(v) > INVALID_HK:
                        v = None
                    values[name] = (v, unit, False)
            if values:
                out.append((_epoch(d, ms), values))
    return out


def parse_hk(log_dir, t_from, t_to, max_points=1500):
    """{name: {"unit", "bool", "t": [...], "v": [...]}} binned to at most max_points
    (numeric: median of the bin, boolean: max, so an alarm in a bin is never hidden)."""
    rows = []
    for path in _files(log_dir, "hk.log"):
        rows.extend(r for r in _cached(path, _parse_hk_file) if t_from <= r[0] <= t_to)
    rows.sort(key=lambda r: r[0])
    if not rows:
        return {}
    width = max((t_to - t_from) / max_points, 10.0)
    series = {}
    for t, values in rows:
        b = int((t - t_from) // width)
        for name, (v, unit, is_bool) in values.items():
            s = series.setdefault(name, {"unit": unit, "bool": is_bool, "bins": {}})
            s["bins"].setdefault(b, []).append(v)
    out = {}
    for name, s in series.items():
        ts, vs = [], []
        prev = None
        for b in sorted(s["bins"]):
            if prev is not None and b - prev > 3:
                # no data for a while (program stopped, missing files): break the line
                ts.append(t_from + (prev + 1.5) * width)
                vs.append(None)
            vals = [v for v in s["bins"][b] if v is not None]
            ts.append(t_from + (b + 0.5) * width)
            # median, not mean: a single absurd sample (e.g. 423 V) must not move the whole bin
            vs.append(None if not vals else (max(vals) if s["bool"] else statistics.median(vals)))
            prev = b
        out[name] = {"unit": s["unit"], "bool": s["bool"], "t": ts, "v": vs}
    return out


# ---------------------------------------------------------------- events

def _parse_hk_events(path):
    """WARNING / ERROR lines of hk.log ("... - housekeeping - LEVEL - message")."""
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HK_RE.match(line.rstrip("\n"))
            if m and m.group(3) in ("WARNING", "ERROR"):
                d, ms, level, msg = m.groups()
                out.append((_epoch(d, ms), "housekeeping", "", level, msg.strip()))
    return out


def parse_events(log_dir, t_from, t_to, limit=300):
    """(most recent `limit` WARNING/ERROR events, all of them in the range)."""
    events = []
    for base, parser in (("run.log", _parse_run_file), ("device.log", _parse_run_file),
                         ("hk.log", _parse_hk_events)):
        for path in _files(log_dir, base):
            for t, cls, func, level, msg in _cached(path, parser):
                if level in ("WARNING", "ERROR") and t_from <= t <= t_to:
                    source = f"{cls}::{func}" if func else cls
                    events.append({"t": t, "file": base, "source": source, "level": level, "msg": msg})
    events.sort(key=lambda e: e["t"], reverse=True)
    return events[:limit], events


def latest_time(log_dir):
    t = 0.0
    for base in ("run.log", "hk.log"):
        for path in _files(log_dir, base)[-2:]:
            parsed = _cached(path, _parse_run_file if base == "run.log" else _parse_hk_file)
            if parsed:
                t = max(t, parsed[-1][0])
    return t


def night_of(t):
    """Observation night: a night from ~22:00 UTC of day D to ~09:00 of D+1 is 'D'."""
    return dt.datetime.fromtimestamp(t - 12 * 3600, dt.timezone.utc).strftime("%Y-%m-%d")
