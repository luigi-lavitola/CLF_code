#!/usr/bin/env python3
"""Read-only dump of the important FPGA run-control registers, decoded.

    python tools/fpga_status.py COM5                 # Windows, hw v2 (122.88 MHz)
    python tools/fpga_status.py /dev/runcontrol --hw 1
    python tools/fpga_status.py COM5 --watch 20      # then 20 s of PPS / d / seconds, once per second

Nothing is written to the FPGA (main.py must not be running: one process per serial port).
Register map: CLF_main_V2/README_timing.md.
"""

import argparse
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.FPGADevice import FPGADevice          # noqa: E402
from lib.GpsTime import unix_to_gps            # noqa: E402
from lib.Hardware import PROFILES              # noqa: E402
from lib import TimeSync                       # noqa: E402

MUX = {0x0: "PPS_out (local PPS)", 0x1: "10 MHz", 0x2: "QSwitch_IN (default)", 0x3: "QSwitch_Out",
       0x4: "Diode_Out", 0x5: "PPS_GPS"}


def bits(value, names):
    return ", ".join(f"{n}={(value >> b) & 1}" for b, n in names)


def utc(unix):
    return datetime.datetime.fromtimestamp(unix, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def d_text(d, tick_ns):
    if d in (0, 0xFFFF):
        return f"{d} (GPS PPS outside the +/-32767 tick window)"
    return f"{d} -> GPS - local PPS = {(d - 32767) * tick_ns:+.0f} ns"


def dump(f, hw):
    tick = hw.tick_ns
    r = f.read_register
    a = f.read_address
    print(f"profile hw v{hw.version}: {hw.clk_hz / 1e6:g} MHz, tick {tick:.3f} ns\n")

    print("== firmware / clocks")
    print(f"fw_version 0xFF       : {r('fw_version'):#06x}  (0 = register not in this firmware)")
    v8 = a(0x08)
    print(f"0x08 locks            : {v8:#06x}  "
          + bits(v8, [(0, "PLL12M"), (2, "jitter_cleaner"), (3, "VCXOLock"), (1, "Lock_10M")]))

    print("\n== PPS / time")
    v7 = a(0x07)
    print(f"0x07 status           : {v7:#06x}  PPS_PRESENT={(v7 >> 8) & 1}, Freq_10M_OK={(v7 >> 7) & 1}")
    v9 = a(0x09)
    print(f"0x09 R_CH_SEL         : {v9:#06x}  "
          + bits(v9, [(0, "clk_internal"), (1, "clk_vcxo"), (2, "manual"), (6, "PID_software"),
                      (7, "PPS_from_GPS")]))
    print(f"0x0B pps_distance d   : {d_text(r('pps_distance'), tick)}")
    tc = r("time_cnt")
    print(f"0x0D time_cnt         : {tc} ticks = {tc * tick / 1e9:.6f} s into the second")
    off = TimeSync.offset(f)                    # waits for mid-second
    sec = r("unixtime")
    print(f"0x00 unixtime         : {sec} = {utc(sec)} UTC, GPS {unix_to_gps(sec)}")
    print(f"     FPGA - PC clock  : {off:+d} s   (PC: {utc(time.time())} UTC; meaningful only if "
          "the PC is NTP-synced)")
    print(f"0x19 arm_unixtime     : {r('arm_unixtime')}")

    print("\n== laser")
    v3 = a(0x03)
    print(f"0x03 control          : {v3:#06x}  "
          + bits(v3, [(0, "laser_start"), (1, "laser_en"), (2, "timestamp_en")]))
    D, E, P, W = r("pps_delay"), r("pulse_energy"), r("pulse_period"), r("pulse_width")
    print(f"0x05 D pps_delay      : {D} ticks = {D * tick / 1e6:.6f} ms")
    print(f"0x14 E pulse_energy   : {E} ticks = {E * tick / 1e3:.3f} us")
    print(f"0x1B P pulse_period   : {P} ticks = {P * tick / 1e6:.6f} ms")
    print(f"0x13 W pulse_width    : {W} ticks = {W * tick:.0f} ns")
    print(f"     trigger (Diode)  : {hw.trigger_time(D, E) * 1e3:.5f} ms after the GPS second")
    print(f"0x22 N shots_num      : {r('shots_num')}")
    print(f"0x24 shots_cnt        : {r('shots_cnt')}")

    print("\n== BNC mux")
    for i in range(5):
        m = r(f"mux_bnc_{i}")
        print(f"0x{0x1D + i:02X} BNC {i}            : {m:#x}  {MUX.get(m, 'QSwitch_IN')}")

    print("\n== digital I/O (default wiring, see conf/<site>/dio.yml)")
    print(f"0x16 inputs           : {a(0x16):#06x}  "
          + ", ".join(f"{n}={int(f.read_dio(n))}" for n, io in f.iomap.items() if io.get_addr() == 0x16))
    print(f"0x17 outputs          : {a(0x17):#06x}  "
          + ", ".join(f"{n}={int(f.read_dio(n))}" for n, io in f.iomap.items() if io.get_addr() == 0x17))


def watch(f, hw, seconds):
    print(f"\n== watch {seconds} s (mid-second samples)")
    print(f"{'PC UTC':19}  {'unixtime':>10}  {'FPGA-PC':>7}  PPS  {'d':>5}  {'GPS-local ns':>12}")
    for _ in range(seconds):
        off = TimeSync.offset(f)
        sec = f.read_register("unixtime")
        d = f.read_register("pps_distance")
        pps = int(f.read_dio("pps_present"))
        ns = "out" if d in (0, 0xFFFF) else f"{(d - 32767) * hw.tick_ns:+.0f}"
        print(f"{utc(time.time()):19}  {sec:10}  {off:+7d}  {pps:3}  {d:5}  {ns:>12}")
        time.sleep(0.6)                          # next sample in the next second


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("port", help="register UART (COM5, /dev/runcontrol, ...)")
    ap.add_argument("--hw", type=int, default=2, choices=sorted(PROFILES), help="hardware version")
    ap.add_argument("--watch", type=int, default=0, metavar="S", help="then sample PPS/d for S seconds")
    a = ap.parse_args(argv)
    f = FPGADevice(a.port)
    try:
        dump(f, PROFILES[a.hw])
        if a.watch:
            watch(f, PROFILES[a.hw], a.watch)
    finally:
        f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
