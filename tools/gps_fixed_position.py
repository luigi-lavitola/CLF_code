#!/usr/bin/env python3
"""
u-blox LEA-M8F: fixed-position (time) mode from the positions logged in hk.log.

With the antenna position known the receiver solves for time only: on the bench
(FS740, 24 h) trigger vs UTC std 11 ns, TDEV ~5 ns at 512 s, against 52 ns / 28 ns
in navigation mode (GPS+GLONASS).

    # 1. look at the average of the last 24 h (hk.log gps_lat/gps_lon/gps_alt, 1 sample ~10 s)
    python3 tools/gps_fixed_position.py [--hours 24 | --night YYYY-MM-DD]

    # 2. same, and send it to the receiver (CFG-TMODE2 fixed + SAVE to flash)
    python3 tools/gps_fixed_position.py --apply

    # known geodetic position instead of the average (height above the ellipsoid, m)
    python3 tools/gps_fixed_position.py --lla LAT LON HAE --apply

    # back to navigation mode (CFG-TMODE2 disabled + SAVE)
    python3 tools/gps_fixed_position.py --nav --apply

Only samples with a usable fix (gps_fix True, no holdover, >= MIN_SATS satellites) are
used; the median is taken (robust against single bad fixes). Messages go through gpsd
with ubxtool, so main.py and gpsd keep running.
"""

import argparse
import datetime as dt
import json
import math
import os
import statistics
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
import logparse as lp                                   # noqa: E402

MIN_SATS = 6
MIN_SAMPLES = 360                   # one hour at ~10 s
DEFAULT_ACC_MM = 2000               # one night of navigation fixes: ~1-2 m (multipath, ionosphere)

# WGS84
A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)


def lla_to_ecef(lat, lon, h):
    la, lo = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return ((n + h) * math.cos(la) * math.cos(lo),
            (n + h) * math.cos(la) * math.sin(lo),
            (n * (1 - E2) + h) * math.sin(la))


def tmode2_payload(mode, ecef_m=(0.0, 0.0, 0.0), acc_mm=0):
    """CFG-TMODE2 (0x06 0x3D), 28 bytes: timeMode, reserved, flags (ECEF), X/Y/Z cm,
    fixedPosAcc mm, svinMinDur s, svinAccLimit mm."""
    x, y, z = (int(round(c * 100)) for c in ecef_m)
    return struct.pack("<BBHiiiIII", mode, 0, 0, x, y, z, int(acc_mm), 0, 0)


def ubx_c_arg(payload):
    return ",".join(f"0x{b:02x}" for b in (0x06, 0x3D) + tuple(payload))


def night_window(night):
    d = dt.datetime.strptime(night, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    t0 = (d + dt.timedelta(hours=12)).timestamp()
    return t0, t0 + 86400


def _v(values, name):
    v = values.get(name)
    return None if v is None else v[0]


def average(log_dir, t0, t1):
    lat, lon, alt = [], [], []
    for _, values in lp.hk_rows(log_dir, t0, t1):
        if _v(values, "gps_fix") != 1 or _v(values, "gps_holdover") == 1:
            continue
        if (_v(values, "gps_sats_used") or 0) < MIN_SATS:
            continue
        p = (_v(values, "gps_lat"), _v(values, "gps_lon"), _v(values, "gps_alt"))
        if None in p:
            continue
        lat.append(p[0]); lon.append(p[1]); alt.append(p[2])
    if not lat:
        return None
    m = (statistics.median(lat), statistics.median(lon), statistics.median(alt))
    m_per_deg_lat = 111132.9
    m_per_deg_lon = 111319.5 * math.cos(math.radians(m[0]))
    north = [(v - m[0]) * m_per_deg_lat for v in lat]
    east = [(v - m[1]) * m_per_deg_lon for v in lon]
    n = len(lat)
    return {"n": n, "lat": m[0], "lon": m[1], "alt": m[2],
            "std_n": statistics.pstdev(north), "std_e": statistics.pstdev(east),
            "std_u": statistics.pstdev(alt),
            # error of the median of correlated fixes: not 1/sqrt(n); keep it simple and honest
            "hours": n * 10 / 3600}


def current_tpv():
    """One TPV report from gpsd (None if gpspipe is not available)."""
    try:
        out = subprocess.run(["gpspipe", "-w", "-n", "20"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("class") == "TPV":
            return msg
    return None


def run(cmd):
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print("\n".join(out.splitlines()[-15:]))
    if r.returncode:
        sys.exit(f"command failed ({r.returncode})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=os.path.join(ROOT, "logs"))
    ap.add_argument("--hours", type=float, default=24, help="average over the last HOURS (default 24)")
    ap.add_argument("--night", help="YYYY-MM-DD: 12:00 UTC that day -> 12:00 next day, instead of --hours")
    ap.add_argument("--lla", nargs=3, type=float, metavar=("LAT", "LON", "HAE"),
                    help="known position (deg, deg, m above the WGS84 ellipsoid) instead of the average")
    ap.add_argument("--acc-mm", type=int, default=None, help=f"fixedPosAcc (default {DEFAULT_ACC_MM} mm)")
    ap.add_argument("--nav", action="store_true", help="disable the time mode (back to navigation)")
    ap.add_argument("--apply", action="store_true", help="send to the receiver and save to flash")
    args = ap.parse_args()

    if args.nav:
        payload = tmode2_payload(0)
        print("CFG-TMODE2 disabled (navigation mode)")
    else:
        if args.lla:
            lat, lon, hae = args.lla
            print(f"known position: lat {lat:.7f} lon {lon:.7f} h(ellipsoid) {hae:.2f} m")
        else:
            if args.night:
                t0, t1 = night_window(args.night)
                what = f"night {args.night}"
            else:
                t1 = dt.datetime.now(dt.timezone.utc).timestamp()
                t0 = t1 - args.hours * 3600
                what = f"last {args.hours:g} h"
            avg = average(args.logs, t0, t1)
            if avg is None:
                sys.exit(f"no usable GPS samples in hk.log ({what})")
            lat, lon, hae = avg["lat"], avg["lon"], avg["alt"]
            print(f"{what}: {avg['n']} samples (~{avg['hours']:.1f} h) with fix, no holdover, "
                  f">= {MIN_SATS} sats")
            print(f"median: lat {lat:.7f} lon {lon:.7f} alt {hae:.2f} m")
            print(f"spread (std): north {avg['std_n']:.2f} m, east {avg['std_e']:.2f} m, up {avg['std_u']:.2f} m")
            if avg["n"] < MIN_SAMPLES:
                sys.exit(f"fewer than {MIN_SAMPLES} samples: not enough for a fixed position")
            tpv = current_tpv()
            if tpv is not None and "altHAE" not in tpv:
                # GpsInfo logs altHAE when gpsd has it, otherwise alt (MSL): convert
                sep = tpv.get("geoidSep")
                if sep is None:
                    sys.exit("gpsd gives neither altHAE nor geoidSep: height reference unknown, use --lla")
                hae += sep
                print(f"gpsd without altHAE: logged alt is MSL, + geoid separation {sep} m -> {hae:.2f} m")
            elif tpv is None:
                print("(gpspipe not available: logged alt assumed above the ellipsoid, as gpsd 3.22 altHAE)")
        acc = args.acc_mm or DEFAULT_ACC_MM
        ecef = lla_to_ecef(lat, lon, hae)
        print(f"ECEF: X {ecef[0]:.2f} Y {ecef[1]:.2f} Z {ecef[2]:.2f} m, fixedPosAcc {acc} mm")
        payload = tmode2_payload(2, ecef, acc)

    cmds = [["ubxtool", "-c", ubx_c_arg(payload)],
            ["ubxtool", "-p", "SAVE"],
            ["ubxtool", "-p", "CFG-TMODE2"]]
    if not args.apply:
        print("\nnot sent (dry run). With --apply, or by hand:")
        for c in cmds:
            print("  " + " ".join(c))
        return
    print()
    for c in cmds:
        run(c)
    print("\ndone. Check in ~1 min: ubxtool -p NAV-PVT  -> fixType 5 (time only) in fixed mode;\n"
          "gpspipe -w -n 10 | grep TPV -> \"mode\":3; hk.log gps_fix=True.")


if __name__ == "__main__":
    main()
