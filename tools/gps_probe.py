#!/usr/bin/env python3
"""Look at what a u-blox GPS (LEA-M8F) sends on its serial port: NMEA and UBX.

    python tools/gps_probe.py COM16                  # Windows, 9600 baud
    python tools/gps_probe.py /dev/gps0 -b 9600      # site PC: stop gpsd first
    python tools/gps_probe.py COM16 --raw            # also print every message
    python tools/gps_probe.py COM16 --poll           # ask version, port and time pulse config
    python tools/gps_probe.py COM16 -t 60 --save gps.bin

Every second prints a decoded summary (time, fix, satellites, DOP, position); at the end the
list of message types with rate and checksum errors, and how much of the baud rate is used.
--poll only sends UBX poll requests (MON-VER, CFG-PRT, CFG-TP5, CFG-NAV5): the configuration
of the receiver is not changed.
"""

import argparse
import collections
import os
import struct
import sys
import time

import serial

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.Ubx import (UBX_SYNC, UBX_NAMES, ubx_checksum, ubx_frame, ubx_name,   # noqa: E402,F401
                     decode_ubx)


# --- NMEA ------------------------------------------------------------------------------------

def nmea_ok(line):
    """'$....*hh' with a valid checksum."""
    star = line.rfind("*")
    if not line.startswith("$") or star < 0 or len(line) < star + 3:
        return False
    s = 0
    for c in line[1:star]:
        s ^= ord(c)
    try:
        return s == int(line[star + 1:star + 3], 16)
    except ValueError:
        return False


def nmea_fields(line):
    return line[1:line.rfind("*")].split(",")


def _float(v):
    try:
        return float(v)
    except ValueError:
        return None


def nmea_coord(v, hemi, deg_digits):
    if not v:
        return None
    x = int(v[:deg_digits]) + float(v[deg_digits:]) / 60
    return -x if hemi in ("S", "W") else x


class State:
    """Last values seen, summarised once per second."""

    GGA_QUALITY = {"0": "no fix", "1": "GPS", "2": "DGPS", "4": "RTK", "5": "RTK float", "6": "dead reckoning"}

    def __init__(self):
        self.time = self.date = self.fix = self.rmc_status = None
        self.used = None
        self.pos = (None, None, None)
        self.dop = (None, None, None)
        self.gsv = {}          # talker -> {prn: snr}
        self.gsv_tmp = {}
        self.sat_used = set()
        self.antenna = None

    def nmea(self, line):
        f = nmea_fields(line)
        talker, kind = f[0][:2], f[0][2:]
        if kind == "RMC" and len(f) >= 10:
            self.time, self.rmc_status, self.date = f[1], f[2], f[9]
        elif kind == "ZDA" and len(f) >= 5:
            self.time, self.date = f[1], f"{f[2]}/{f[3]}/{f[4]}"
        elif kind == "GGA" and len(f) >= 10:
            self.fix = self.GGA_QUALITY.get(f[6], f[6])
            self.used = f[7]
            self.pos = (nmea_coord(f[2], f[3], 2), nmea_coord(f[4], f[5], 3), _float(f[9]))
        elif kind == "GSA" and len(f) >= 18:
            self.dop = tuple(_float(v) for v in f[15:18])
            self.fix_mode = {"1": "no fix", "2": "2D", "3": "3D"}.get(f[2], f[2])
            self.sat_used |= {p for p in f[3:15] if p}
        elif kind == "GSV" and len(f) >= 4:
            total, num = int(f[1] or 0), int(f[2] or 0)
            if num == 1:
                self.gsv_tmp[talker] = {}
            sats = self.gsv_tmp.setdefault(talker, {})
            for i in range(4, len(f) - 3, 4):
                if f[i]:
                    sats[f[i]] = _float(f[i + 3]) if f[i + 3] else None
            if num == total:
                self.gsv[talker] = sats
        elif kind == "TXT" and len(f) >= 5:
            if "ANTSTATUS" in f[4] or "ANTSUPERV" in f[4]:
                self.antenna = f[4]

    def summary(self):
        sats = [snr for t in self.gsv.values() for snr in t.values()]
        tracked = [s for s in sats if s]
        snr = f"{sum(tracked) / len(tracked):.0f} dBHz (max {max(tracked):.0f})" if tracked else "-"
        per_sys = " ".join(f"{t}:{len(v)}" for t, v in sorted(self.gsv.items()))
        lat, lon, alt = self.pos
        pos = f"{lat:.6f} {lon:.6f} {alt} m" if lat is not None else "-"
        out = (f"{self.date or '-'} {self.time or '-'} UTC | fix {self.fix or '-'} "
               f"(RMC {self.rmc_status or '-'}) | used {self.used or '-'} | visible {len(sats)} ({per_sys}) "
               f"| with signal {len(tracked)}, SNR {snr} | PDOP/HDOP/VDOP {self.dop} | {pos}")
        if self.antenna:
            out += f" | {self.antenna}"
        self.sat_used = set()
        return out


# --- reader ----------------------------------------------------------------------------------

class Reader:
    def __init__(self, raw=False, quiet=False):
        self.buf = b""
        self.raw = raw
        self.quiet = quiet          # do not print UBX messages (read them from self.ubx)
        self.ubx = {}               # name -> (payload, monotonic time) of the last UBX message
        self.state = State()
        self.count = collections.Counter()
        self.bad = collections.Counter()
        self.nbytes = 0
        self.garbage = 0

    def feed(self, data):
        self.nbytes += len(data)
        self.buf += data
        while True:
            i_n, i_u = self.buf.find(b"$"), self.buf.find(UBX_SYNC)
            starts = [i for i in (i_n, i_u) if i >= 0]
            if not starts:
                self.garbage += max(len(self.buf) - 1, 0)
                self.buf = self.buf[-1:]
                return
            start = min(starts)
            self.garbage += start
            self.buf = self.buf[start:]
            if start == i_u:
                if not self._ubx():
                    return
            elif not self._nmea():
                return

    def _nmea(self):
        end = self.buf.find(b"\n")
        if end < 0:
            if len(self.buf) > 200:          # NMEA lines are < 83 chars: lost the end
                self.bad["NMEA ?"] += 1
                self.buf = self.buf[1:]
                return True
            return False
        line = self.buf[:end].decode("ascii", "replace").strip()
        self.buf = self.buf[end + 1:]
        name = line[1:].split(",", 1)[0] if line.startswith("$") else "?"
        if not nmea_ok(line):
            self.bad[name] += 1
            if self.raw:
                print(f"  BAD  {line}")
            return True
        self.count[name] += 1
        self.state.nmea(line)
        if self.raw:
            print(f"  {line}")
        return True

    def _ubx(self):
        if len(self.buf) < 6:
            return False
        cls, mid, length = self.buf[2], self.buf[3], struct.unpack_from("<H", self.buf, 4)[0]
        if length > 4096:
            self.buf = self.buf[2:]
            return True
        if len(self.buf) < 8 + length:
            return False
        body, ck = self.buf[2:6 + length], self.buf[6 + length:8 + length]
        name = ubx_name(cls, mid)
        if ubx_checksum(body) != ck:
            self.bad[name] += 1
            self.buf = self.buf[2:]
            return True
        self.buf = self.buf[8 + length:]
        self.count[name] += 1
        self.ubx[name] = (body[4:], time.monotonic())
        if self.quiet:
            return True
        text = decode_ubx(cls, mid, body[4:])
        if text is not None or self.raw:
            print(f"  {name} ({length} B): {text if text is not None else body[4:].hex()}")
        return True


POLLS = [("MON-VER", ubx_frame(0x0A, 0x04)),
         ("CFG-PRT", ubx_frame(0x06, 0x00, b"\x01")),          # UART1
         ("CFG-TP5", ubx_frame(0x06, 0x31, b"\x00")),          # TIMEPULSE (PPS)
         ("CFG-TP5", ubx_frame(0x06, 0x31, b"\x01")),          # TIMEPULSE2
         ("CFG-NAV5", ubx_frame(0x06, 0x24))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("port", help="serial port (COM16, /dev/gps0, ...)")
    ap.add_argument("-b", "--baud", type=int, default=9600)
    ap.add_argument("-t", "--duration", type=float, default=15, help="seconds to read (0 = until Ctrl+C)")
    ap.add_argument("--raw", action="store_true", help="print every message")
    ap.add_argument("--poll", action="store_true", help="send UBX poll requests (read only)")
    ap.add_argument("--save", help="also write the raw bytes to this file")
    a = ap.parse_args(argv)

    ser = serial.Serial(a.port, a.baud, timeout=0.1)
    out = open(a.save, "wb") if a.save else None
    r = Reader(raw=a.raw)
    ser.reset_input_buffer()
    if a.poll:
        for name, frame in POLLS:
            ser.write(frame)
        ser.flush()
    t0 = last = time.monotonic()
    try:
        while not a.duration or time.monotonic() - t0 < a.duration:
            data = ser.read(4096)
            if data:
                r.feed(data)
                if out:
                    out.write(data)
            if time.monotonic() - last >= 1:
                last = time.monotonic()
                print(r.state.summary())
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        if out:
            out.close()

    elapsed = time.monotonic() - t0
    print(f"\n{a.port} @ {a.baud} baud, {elapsed:.1f} s, {r.nbytes} bytes "
          f"({r.nbytes / elapsed:.0f} B/s = {r.nbytes * 10 / elapsed / a.baud:.0%} of the line)"
          + (f", {r.garbage} bytes outside messages" if r.garbage else ""))
    print(f"{'message':14} {'count':>6} {'per s':>6} {'bad':>4}")
    for name in sorted(set(r.count) | set(r.bad)):
        print(f"{name:14} {r.count[name]:6} {r.count[name] / elapsed:6.2f} {r.bad[name]:4}")
    if a.poll:
        missing = {n for n, _ in POLLS} - set(r.count)
        if missing:
            print(f"no answer to: {', '.join(sorted(missing))} (UBX input disabled on this port?)")
    if r.nbytes * 10 / elapsed / a.baud > 0.8:
        print("WARNING: line almost full, messages may be dropped: raise the baud rate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
