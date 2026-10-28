#!/usr/bin/env python3
"""GPS (u-blox LEA-M8F) and FPGA side by side, once per second: is the PPS still from GNSS?

    python tools/gps_fpga_monitor.py COM16 COM5                  # until Ctrl+C
    python tools/gps_fpga_monitor.py /dev/gps0 /dev/runcontrol -b 115200 -t 600 --csv mon.csv

Per second:
  GPS   time, RMC status (A valid / V not), fix quality, satellites used, mean SNR
  SMGR  UBX MON-SMGR of the sync manager (polled, read only): GNSS available, internal
        oscillator state / calibrated / disciplined, disciplining source, raw words
  FPGA  PPS_PRESENT, pps_distance d, GPS - local PPS in ns, drift of d since the start

Holdover = GPS without fix / GNSS not available, while the FPGA still sees the PPS and d
slowly drifts. Nothing is written to the FPGA; gpsd and main.py must not use the two ports.
"""

import argparse
import csv
import datetime
import os
import struct
import sys
import time

import serial

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.FPGADevice import FPGADevice          # noqa: E402
from lib.Hardware import PROFILES              # noqa: E402
import gps_probe                               # noqa: E402

POLL_SMGR = gps_probe.ubx_frame(0x0A, 0x2E)
OSC_STATE = {0: "autonomous", 1: "calibrating", 2: "host-steered", 3: "idle"}
DISC_SRC = {0: "internal", 1: "GNSS", 2: "EXTINT0", 3: "EXTINT1", 4: "int.host", 5: "ext.host"}


def decode_smgr(p):
    """MON-SMGR payload (16 B) -> dict, None if missing/short."""
    if p is None or len(p) < 16:
        return None
    _, int_osc, ext_osc, disc, gnss, ext0, ext1 = struct.unpack_from("<IHHBBBB", p, 4)
    return {"gnss_avail": gnss & 1,
            "osc_state": OSC_STATE.get(int_osc & 0xF, int_osc & 0xF),
            "osc_calib": (int_osc >> 4) & 1,
            "osc_disc": (int_osc >> 5) & 1,
            "disc_src": DISC_SRC.get(disc, disc),
            "raw": f"int={int_osc:04x} ext={ext_osc:04x} src={disc} gnss={gnss:02x}"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("gps_port")
    ap.add_argument("fpga_port")
    ap.add_argument("-b", "--baud", type=int, default=9600, help="GPS baud rate")
    ap.add_argument("--hw", type=int, default=2, choices=sorted(PROFILES))
    ap.add_argument("-t", "--duration", type=float, default=0, help="seconds (0 = until Ctrl+C)")
    ap.add_argument("--csv", help="also write the samples to this CSV file")
    a = ap.parse_args(argv)

    tick = PROFILES[a.hw].tick_ns
    gps = serial.Serial(a.gps_port, a.baud, timeout=0)
    fpga = FPGADevice(a.fpga_port)
    reader = gps_probe.Reader(quiet=True)
    st = reader.state
    out = writer = None
    if a.csv:
        out = open(a.csv, "w", newline="")
        writer = csv.writer(out)
        writer.writerow(["pc_utc", "gps_time", "rmc", "fix", "used", "snr", "gnss_avail", "osc_state",
                         "osc_calib", "osc_disc", "disc_src", "smgr_raw", "pps_present", "d", "ns", "d_drift"])

    print(f"{'PC UTC':8} | {'GPS UTC':9} RMC {'fix':6} used  SNR | GNSS osc{'':10} cal dis src{'':5}"
          f"| PPS     d     ns  drift | MON-SMGR raw")
    gps.reset_input_buffer()
    d0 = None
    last_n = -1
    t0 = time.monotonic()
    try:
        while not a.duration or time.monotonic() - t0 < a.duration:
            # poll at ~0.3 s, sample everything at mid-second (away from the PPS edges)
            time.sleep((1.3 - time.time() % 1) % 1)
            gps.write(POLL_SMGR)
            time.sleep((1.5 - time.time() % 1) % 1)
            reader.feed(gps.read(65536))

            smgr_p, smgr_t = reader.ubx.get("MON-SMGR", (None, 0))
            smgr = decode_smgr(smgr_p) if time.monotonic() - smgr_t < 1.5 else None
            pps = int(fpga.read_dio("pps_present"))
            d = fpga.read_register("pps_distance")
            inside = d not in (0, 0xFFFF)
            ns = (d - 32767) * tick if inside else None
            if inside and d0 is None:
                d0 = d
            drift = d - d0 if inside and d0 is not None else None

            sats = [s for t in st.gsv.values() for s in t.values() if s]
            snr = sum(sats) / len(sats) if sats else None
            n_msg = sum(reader.count.values())
            gps_time = st.time[:6] if st.time else "-"
            if n_msg == last_n:                              # no NMEA/UBX in the last second
                gps_time = "SILENT"
            last_n = n_msg
            pc = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
            sm = smgr or {"gnss_avail": "-", "osc_state": "-", "osc_calib": "-", "osc_disc": "-",
                          "disc_src": "-", "raw": "no answer"}
            print(f"{pc:8} | {gps_time:9} {st.rmc_status or '-':3} {(st.fix or '-')[:6]:6} {st.used or '-':>4} "
                  f"{'-' if snr is None else round(snr):>4} | {sm['gnss_avail']!s:4} {sm['osc_state']!s:13} "
                  f"{sm['osc_calib']!s:3} {sm['osc_disc']!s:3} {sm['disc_src']!s:8}| {pps:3} {d:5} "
                  f"{'out' if ns is None else f'{ns:+.0f}':>6} {'' if drift is None else f'{drift:+d}':>6} "
                  f"| {sm['raw']}", flush=True)
            if writer:
                writer.writerow([pc, st.time, st.rmc_status, st.fix, st.used,
                                 None if snr is None else round(snr, 1), sm["gnss_avail"], sm["osc_state"],
                                 sm["osc_calib"], sm["osc_disc"], sm["disc_src"], sm["raw"], pps, d,
                                 None if ns is None else round(ns), drift])
                out.flush()
    except KeyboardInterrupt:
        pass
    finally:
        gps.close()
        fpga.close()
        if out:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
