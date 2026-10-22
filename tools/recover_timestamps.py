#!/usr/bin/env python3
"""
Recover laser shot timestamps from CLF/XLF run logs written before the
FPGAData parser fix.

THE BUG
-------
Every version of lib/FPGAData.py up to the fix decoded the sub-second tick as

    counter = (hi << 16) + lo * 10          # wrong: only the low word scaled

instead of

    counter = ((hi << 16) + lo) * 10        # ns since the local PPS

where tick = (hi << 16) | lo is the FPGA counter (10 ns per tick, < 1e8).
The same bug affected the "width" field of the oldest log format.

WHY IT IS RECOVERABLE
---------------------
logged = 65536*hi + 10*lo. Solving 10*lo = logged (mod 65536) gives at most
two solutions, (hi, lo) and (hi-5, lo+32768), whose ticks differ by
294912 ticks = 2.949 ms. The right one is the one close to the nominal shot
time (pps_delay + pulse_energy). The nominal times are >= 100 ms apart, so
the choice is never ambiguous.

INPUT
-----
Run log files (logs/run.log, logs/run.log.YYYY-MM-DD, ...) or directories
containing them. Recognised shot lines:

  ... - RunFD::run - INFO - power 3 shot: 1.23, seconds: 1735689600, counter: 25271556, pps distance: -30ns, counter cycle: 4
  ... - power 3 shot: 1.23, seconds: 1735689600, counter: 25271556, width: 10010     (format before 2025-04-04)

OUTPUT (CSV)
------------
  file, line, log_time, run_class, phase, shot_index, power,
  seconds              UNIX second from the FPGA
  counter_logged       wrong value found in the log
  tick                 recovered FPGA tick (10 ns) since the local PPS
  t_local_ns           tick * 10
  pps_distance_ns      as logged: (d - 32767) * 10, d = PPS error word
  t_gps_ns             t_local_ns - (pps_distance_ns - 10): time from the GPS
                       second, using the exact firmware zero (d = 32768)
  counter_cycle        shot number from the FPGA (1 = first shot)
  width_logged, width_ticks   (old format only)
  nominal_ms           nominal shot time used for the choice
  residual_us          t_local - nominal
  n_candidates         1 or 2
  status               ok | check (residual > --tolerance-ms) | no_data
                       (failed FPGA read, all zeros) | invalid

Times do not include the 1-2 tick synchroniser latency of the FPGA input.

One CSV is written per input log file, in --outdir:
  run.log.2026-01-20   ->  shots_2026-01-20.csv   (date of the rotating handler)
  run.log              ->  shots_<date of first line>_current.csv
  anything else        ->  shots_<file name>.csv
Files with no shot lines produce no CSV.

USAGE
-----
  python3 recover_timestamps.py logs/ -d csv/
  python3 recover_timestamps.py run.log.2025-* --nominal-ms 349.99 -d out/
  python3 recover_timestamps.py --selftest
"""

import argparse
import csv
import glob
import os
import re
import sys

TICK_NS = 10
TICKS_PER_S = 100_000_000
INV5_MOD_32768 = pow(5, -1, 32768)

# pps_delay values used so far (ticks) + pulse_energy (17 400 ticks)
PULSE_ENERGY = 17_400
KNOWN_PPS_DELAYS = [
    0,           # calib
    24_982_000,  # clf fd
    34_982_000,  # xlf fd
    49_982_000,  # clf tank
    69_982_000,  # xlf tank
]

SHOT_RE = re.compile(
    r"power (?P<idx>\d+) shot: (?P<power>[^,]*), "
    r"seconds: (?P<sec>-?\d+), counter: (?P<cnt>-?\d+)"
    r"(?:, width: (?P<width>-?\d+)"
    r"|, pps distance: (?P<pps>-?\d+)ns, counter cycle: (?P<cyc>-?\d+))?"
)
HEAD_RE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) - "
    r"(?P<cls>\w+)::(?P<func>\w+) - (?P<lvl>\w+) - (?P<msg>.*)$"
)
PHASE_RE = re.compile(r"^(start .*Run.*|Starting .*)$")


def candidates(logged):
    """All ticks t with 0 <= t < 2**27 such that buggy(t) == logged."""
    if logged < 0 or logged % 2:
        return []
    lo0 = ((logged // 2) * INV5_MOD_32768) % 32768
    out = []
    for lo in (lo0, lo0 + 32768):
        rest = logged - 10 * lo
        if rest >= 0 and rest % 65536 == 0:
            hi = rest // 65536
            if hi < 2 ** 11:
                out.append((hi << 16) | lo)
    return sorted(out)


def buggy(tick):
    """What the old parser logged for a given tick (used by the self-test)."""
    return ((tick >> 16) << 16) + (tick & 0xFFFF) * 10


def circ_dist(a, b):
    d = abs(a - b) % TICKS_PER_S
    return min(d, TICKS_PER_S - d)


def choose(cands, nominals):
    """Candidate closest to any nominal time -> (tick, nominal, signed residual)."""
    best = None
    for t in cands:
        for n in nominals:
            d = circ_dist(t, n)
            if best is None or d < best[0]:
                best = (d, t, n)
    _, t, n = best
    r = (t - n) % TICKS_PER_S
    if r > TICKS_PER_S // 2:
        r -= TICKS_PER_S
    return t, n, r


def iter_files(paths):
    for p in paths:
        matches = glob.glob(p) or [p]
        for m in matches:
            if os.path.isdir(m):
                for f in sorted(os.listdir(m)):
                    if f.startswith("run.log"):
                        yield os.path.join(m, f)
            else:
                yield m


ROTATED_RE = re.compile(r"run\.log\.(\d{4}-\d\d-\d\d)$")


def csv_name(path, rows):
    """shots_<date>.csv from the rotating-handler suffix, see module doc."""
    base = os.path.basename(path)
    m = ROTATED_RE.match(base)
    if m:
        return f"shots_{m.group(1)}.csv"
    if base == "run.log":
        first = next((r["log_time"][:10] for r in rows if r["log_time"]), "")
        return f"shots_{first}_current.csv" if first else "shots_current.csv"
    return f"shots_{base}.csv"


def process_file(path, nominals, tolerance_ticks):
    rows = []
    phase = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            head = HEAD_RE.match(line)
            msg = head.group("msg") if head else line
            cls = head.group("cls") if head else ""
            if PHASE_RE.match(msg):
                phase[cls] = msg
                continue
            m = SHOT_RE.search(msg)
            if not m:
                continue

            sec = int(m.group("sec"))
            logged = int(m.group("cnt"))
            pps = m.group("pps")
            row = {
                "file": path,
                "line": lineno,
                "log_time": head.group("ts") if head else "",
                "run_class": cls,
                "phase": phase.get(cls, ""),
                "shot_index": m.group("idx"),
                "power": m.group("power").strip(),
                "seconds": sec,
                "counter_logged": logged,
                "pps_distance_ns": pps if pps is not None else "",
                "counter_cycle": m.group("cyc") or "",
                "width_logged": m.group("width") or "",
            }

            if sec == 0 and logged == 0:
                row["status"] = "no_data"
            else:
                cands = candidates(logged)
                if not cands:
                    row["status"] = "invalid"
                else:
                    tick, nom, res = choose(cands, nominals)
                    row.update({
                        "tick": tick,
                        "t_local_ns": tick * TICK_NS,
                        "nominal_ms": nom * TICK_NS / 1e6,
                        "residual_us": res * TICK_NS / 1e3,
                        "n_candidates": len(cands),
                        "status": "ok" if abs(res) <= tolerance_ticks else "check",
                    })
                    if pps is not None:
                        row["t_gps_ns"] = tick * TICK_NS - (int(pps) - TICK_NS)
            if row["width_logged"]:
                wc = candidates(int(row["width_logged"]))
                row["width_ticks"] = wc[0] if wc else ""
            rows.append(row)
    return rows


FIELDS = [
    "file", "line", "log_time", "run_class", "phase", "shot_index", "power",
    "seconds", "counter_logged", "tick", "t_local_ns", "pps_distance_ns",
    "t_gps_ns", "counter_cycle", "width_logged", "width_ticks",
    "nominal_ms", "residual_us", "n_candidates", "status",
]


def selftest():
    import random
    rnd = random.Random(1)
    ticks = [0, 1, 17_412, 24_999_450, 49_999_431, 99_999_999]
    ticks += [rnd.randrange(TICKS_PER_S) for _ in range(100_000)]
    for t in ticks:
        c = candidates(buggy(t))
        assert t in c and len(c) <= 2, (t, c)
    nominals = [d + PULSE_ENERGY for d in KNOWN_PPS_DELAYS]
    for n in nominals:
        for jitter in (-50_000, -600, 0, 600, 50_000):   # up to +-0.5 ms
            t = (n + jitter) % TICKS_PER_S
            assert choose(candidates(buggy(t)), nominals)[0] == t, (n, jitter)
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(
        description="Recover laser timestamps from run logs affected by the FPGAData parser bug.")
    ap.add_argument("paths", nargs="*", help="run.log files, globs or directories")
    ap.add_argument("-d", "--outdir", default=".",
                    help="directory for the CSV files, one per log file (default: current dir)")
    ap.add_argument("--nominal-ms", type=float, action="append", default=[],
                    help="extra nominal shot time in ms after the PPS (repeatable)")
    ap.add_argument("--tolerance-ms", type=float, default=0.5,
                    help="residual above which a row is marked 'check' (default 0.5 ms)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.paths:
        ap.error("no input files")

    nominals = [d + PULSE_ENERGY for d in KNOWN_PPS_DELAYS]
    nominals += [round(ms * 1e6 / TICK_NS) for ms in args.nominal_ms]
    tol = round(args.tolerance_ms * 1e6 / TICK_NS)

    os.makedirs(args.outdir, exist_ok=True)
    used = set()
    for path in iter_files(args.paths):
        rows = process_file(path, nominals, tol)
        if not rows:
            print(f"{path}: no shot lines, skipped", file=sys.stderr)
            continue
        name = csv_name(path, rows)
        stem, n = name[:-4], 2
        while name in used:                 # same date from different dirs
            name, n = f"{stem}_{n}.csv", n + 1
        used.add(name)
        out_path = os.path.join(args.outdir, name)
        with open(out_path, "w", newline="") as out:
            w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        stats = {s: sum(r["status"] == s for r in rows)
                 for s in ("ok", "check", "no_data", "invalid")}
        print(f"{path} -> {out_path}: " + " ".join(f"{k}={v}" for k, v in stats.items()),
              file=sys.stderr)


if __name__ == "__main__":
    main()
