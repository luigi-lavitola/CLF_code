"""
u-blox UBX binary protocol: framing, names, decoding.

Used by tools/gps_probe.py (direct serial port) and lib/GpsInfo.py (raw data passed
through by gpsd). decode_ubx() gives readable text, decode_fields() the values used by
the housekeeping.
"""

import struct


UBX_SYNC = b"\xb5\x62"
UBX_NAMES = {
    (0x01, 0x07): "NAV-PVT", (0x01, 0x21): "NAV-TIMEUTC", (0x01, 0x35): "NAV-SAT",
    (0x01, 0x03): "NAV-STATUS", (0x01, 0x20): "NAV-TIMEGPS", (0x01, 0x22): "NAV-CLOCK",
    (0x05, 0x01): "ACK-ACK", (0x05, 0x00): "ACK-NAK",
    (0x06, 0x00): "CFG-PRT", (0x06, 0x31): "CFG-TP5", (0x06, 0x24): "CFG-NAV5",
    (0x06, 0x3D): "CFG-TMODE2", (0x06, 0x71): "CFG-TMODE3", (0x06, 0x62): "CFG-SMGR",
    (0x0A, 0x04): "MON-VER", (0x0A, 0x09): "MON-HW",
    (0x0D, 0x01): "TIM-TP", (0x0D, 0x03): "TIM-TM2", (0x0D, 0x04): "TIM-SVIN",
    (0x0D, 0x10): "TIM-SMEAS", (0x0D, 0x11): "TIM-VCOCAL", (0x0D, 0x15): "TIM-FCHG",
    (0x0D, 0x16): "TIM-HOC", (0x0D, 0x12): "TIM-TOS", (0x0A, 0x2E): "MON-SMGR",
}


def ubx_checksum(body):
    a = b = 0
    for c in body:
        a = (a + c) & 0xFF
        b = (b + a) & 0xFF
    return bytes((a, b))


def ubx_frame(cls, mid, payload=b""):
    body = bytes((cls, mid)) + struct.pack("<H", len(payload)) + payload
    return UBX_SYNC + body + ubx_checksum(body)


def ubx_name(cls, mid):
    return UBX_NAMES.get((cls, mid), f"UBX-{cls:02X}-{mid:02X}")


def decode_ubx(cls, mid, p):
    """Readable text for the messages we care about, None for the others."""
    name = ubx_name(cls, mid)
    if name == "MON-VER":
        sw, hw = p[:30].rstrip(b"\0").decode(), p[30:40].rstrip(b"\0").decode()
        ext = [p[i:i + 30].rstrip(b"\0").decode() for i in range(40, len(p), 30)]
        return f"sw {sw}, hw {hw}" + "".join(f"\n      {e}" for e in ext)
    if name == "CFG-PRT" and len(p) >= 20:
        port, mode, baud, inp, out = p[0], *struct.unpack_from("<IIHH", p, 4)
        protos = lambda m: "+".join(n for b, n in ((1, "UBX"), (2, "NMEA"), (4, "RTCM2"), (32, "RTCM3"))
                                    if m & b) or "none"
        return f"port {port}: {baud} baud, mode 0x{mode:08X}, in {protos(inp)}, out {protos(out)}"
    if name == "CFG-TP5" and len(p) >= 32:
        (idx, ver, cable, rfgroup, freq, freq_lock, length, length_lock,
         delay, flags) = struct.unpack_from("<BBxxhhIIIIiI", p)
        is_freq, is_len = bool(flags & 0x08), bool(flags & 0x10)
        f = (lambda v: f"{v} Hz") if is_freq else (lambda v: f"period {v} us")
        ln = (lambda v: f"length {v} us") if is_len else (lambda v: f"duty {v / 2**32:.3f}")
        return (f"TIMEPULSE{idx + 1}: active={bool(flags & 1)} lockGnssFreq={bool(flags & 2)} "
                f"lockedOtherSet={bool(flags & 4)}\n"
                f"      locked: {f(freq_lock)}, {ln(length_lock)}   not locked: {f(freq)}, {ln(length)}\n"
                f"      alignToTow={bool(flags & 0x20)} polarity={'rising' if flags & 0x40 else 'falling'} "
                f"gridUtcGps={'GPS' if flags & 0x780 else 'UTC'} cable delay {cable} ns, "
                f"rf group delay {rfgroup} ns, user delay {delay} ns, flags 0x{flags:X}")
    if name == "CFG-NAV5" and len(p) >= 36:
        dyn = {0: "portable", 2: "stationary", 3: "pedestrian", 4: "automotive"}.get(p[2], p[2])
        fix = {1: "2D only", 2: "3D only", 3: "auto 2D/3D"}.get(p[3], p[3])
        return f"dynamic model {dyn}, fix mode {fix}, min elevation {struct.unpack_from('<b', p, 12)[0]} deg"
    if name == "NAV-PVT" and len(p) >= 92:
        y, mo, d, h, mi, s, valid = struct.unpack_from("<HBBBBBB", p, 4)
        fix, flags, nsv = p[20], p[21], p[23]
        lon, lat, height = struct.unpack_from("<iii", p, 24)
        return (f"{y:04}-{mo:02}-{d:02} {h:02}:{mi:02}:{s:02} valid 0x{valid:X} fix {fix} "
                f"ok={bool(flags & 1)} sats {nsv} lat {lat * 1e-7:.6f} lon {lon * 1e-7:.6f} "
                f"h {height / 1000:.1f} m")
    if name == "TIM-TP" and len(p) >= 16:
        tow, sub, qerr, week, flags = struct.unpack_from("<IIiHB", p)
        return f"next pulse week {week} tow {tow / 1000:.3f} s, qErr {qerr} ps, flags 0x{flags:X}"
    if name in ("ACK-ACK", "ACK-NAK") and len(p) >= 2:
        return ubx_name(p[0], p[1])
    return None


# --- values for the housekeeping ---------------------------------------------------------------

DISC_SRC = {0: "internal", 1: "GNSS", 2: "EXTINT0", 3: "EXTINT1", 4: "int.host", 5: "ext.host"}


def decode_fields(name, p):
    """{field: value} from the messages used by GpsInfo, None for the others / short payloads."""
    if name == "NAV-TIMEGPS" and len(p) >= 16:
        _, _, _, leap, valid, tacc = struct.unpack_from("<IihbBI", p)
        return {"tow_valid": valid & 1, "week_valid": valid >> 1 & 1, "leap_valid": valid >> 2 & 1,
                "leap_s": leap, "tacc_ns": tacc}
    if name == "NAV-CLOCK" and len(p) >= 20:
        _, bias, drift, tacc, facc = struct.unpack_from("<IiiII", p)
        return {"clk_bias_ns": bias, "clk_drift_ns_s": drift, "clk_tacc_ns": tacc, "clk_facc_ps_s": facc}
    if name == "MON-SMGR" and len(p) >= 16:
        _, int_osc, _, disc, gnss = struct.unpack_from("<IHHBB", p, 4)
        return {"disc_src": disc, "disc_src_name": DISC_SRC.get(disc, str(disc)),
                "osc_state": int_osc & 0xF, "osc_calibrated": int_osc >> 4 & 1,
                "osc_disciplined": int_osc >> 5 & 1, "gnss_avail": gnss & 1}
    if name == "MON-HW" and len(p) >= 60:
        noise, agc = struct.unpack_from("<HH", p, 16)
        return {"noise": noise, "agc": agc, "ant_status": p[20], "ant_power": p[21], "jam": p[45]}
    return None


class UbxStream:
    """Extract UBX frames from a byte stream (NMEA and other bytes in between are skipped)."""

    MAX_LEN = 4096

    def __init__(self):
        self.buf = b""
        self.bad = 0                # frames with a wrong checksum

    def feed(self, data):
        """Add bytes, return the list of complete (name, payload) frames found."""
        self.buf += data
        out = []
        while True:
            i = self.buf.find(UBX_SYNC)
            if i < 0:
                self.buf = self.buf[-1:]            # may be the first sync byte
                return out
            self.buf = self.buf[i:]
            if len(self.buf) < 6:
                return out
            cls, mid, length = self.buf[2], self.buf[3], struct.unpack_from("<H", self.buf, 4)[0]
            if length > self.MAX_LEN:
                self.buf = self.buf[2:]
                continue
            if len(self.buf) < 8 + length:
                return out
            body, ck = self.buf[2:6 + length], self.buf[6 + length:8 + length]
            if ubx_checksum(body) != ck:
                self.bad += 1
                self.buf = self.buf[2:]
                continue
            self.buf = self.buf[8 + length:]
            out.append((ubx_name(cls, mid), body[4:]))
