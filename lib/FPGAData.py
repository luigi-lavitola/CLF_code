"""
Reader of the timestamp packets sent by the FPGA (UART_USB_DATA, /dev/data0).

One packet per laser shot (falling edge of QSwitch_IN), 40 ASCII characters:

    BAAB\\r SSSS\\r ssss\\r TTTT\\r tttt\\r DDDD\\r CCCC\\r FEEF\\r

  S/s  seconds counter, high/low word (UNIX time)
  T/t  ticks since the local PPS, high/low word
  D    PPS error word (0x7FFF ~ local PPS aligned with GPS)
  C    shot number of the current sequence (1 = first shot after laser_start)

The stream is buffered across calls and frames are recognised strictly, so that
several packets in the serial buffer, a frame split over two reads or a corrupt
frame never shift or drop the following packets.
"""

import logging
import re
import time
from collections import deque
from functools import partial
from typing import NamedTuple

import serial

FRAME_RE = re.compile(r"BAAB\r" + r"([0-9A-Fa-f]{4})\r" * 6 + r"FEEF\r")
FRAME_LEN = 40
POLL_S = 0.05
_now = time.monotonic      # module level, so that tests can replace the clock
_sleep = time.sleep

_TEMPLATE = "BAAB\r" + "HHHH\r" * 6 + "FEEF\r"      # H = hex digit
_HEX = set("0123456789ABCDEFabcdef")


def _frame_prefix(text):
    """True if text can be the beginning of a frame still being received."""
    return len(text) < FRAME_LEN and all(
        (c in _HEX) if t == "H" else (c == t) for c, t in zip(text, _TEMPLATE))


class Packet(NamedTuple):
    seconds: int        # UNIX seconds from the FPGA counter
    counter: float      # ns since the local PPS
    pps_delta: float    # ns, (d - 32767) * tick
    shot: int           # shot number in the sequence (1 = first)
    raw: str


class FPGAData:
    _instance = None

    HEADER = 'BAAB'
    FOOTER = 'FEEF'
    PACKET_SIZE = FRAME_LEN

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FPGAData, cls).__new__(cls)
        return cls._instance

    def __init__(self, port, baudrate=115200):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self.port = port
        self.baudrate = baudrate
        self._setup()

        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.5)
        except serial.SerialException as e:
            raise RuntimeError(f"Errore apertura porta seriale: {e}")

    def _setup(self, tick_ns=10.0):
        self.buffer = ""                # characters received and not consumed yet
        self.pending = deque()          # parsed packets kept for a later read_shot()
        self.tick_ns = tick_ns          # FPGA clock period, set from the hw profile by DeviceCollection.init()
        self.log = partial(logging.getLogger("run").log, extra={'classname': self.__class__.__name__})

    # ---- stream handling ----------------------------------------------------------------

    def _fill(self):
        # 'replace': a corrupt byte becomes U+FFFD and invalidates its frame, instead of
        # being dropped silently ('ignore') and shifting the following fields
        self.buffer += self.serial.read_all().decode('ascii', 'replace')

    def _next_frame(self):
        """Consume and return the next complete valid frame in the buffer, or None."""
        m = FRAME_RE.search(self.buffer)
        if m:
            junk = self.buffer[:m.start()]
            self.buffer = self.buffer[m.end():]
            if junk.strip():
                self.log(logging.ERROR, f"discarded {len(junk)} chars before a packet: {junk!r}")
            return self._parse_fields(m.groups(), m.group(0))

        # no complete frame: keep only the frame still arriving, i.e. the leftmost position
        # of the last FRAME_LEN-1 chars from which the text is a valid frame prefix
        # (not rfind('BAAB'): a data word can be BAAB too)
        n = len(self.buffer)
        start = next((i for i in range(max(0, n - FRAME_LEN + 1), n)
                      if _frame_prefix(self.buffer[i:])), n)
        junk = self.buffer[:start]
        tail = self.buffer[start:]
        if junk.strip():
            self.log(logging.ERROR, f"discarded invalid data: {junk!r}")
        self.buffer = tail
        return None

    def _parse_fields(self, words, raw):
        v = [int(w, 16) for w in words]
        return Packet(seconds=(v[0] << 16) + v[1],
                      counter=((v[2] << 16) + v[3]) * self.tick_ns,
                      pps_delta=(v[4] - 32767) * self.tick_ns,
                      shot=v[5],
                      raw=raw)

    def read_packet(self, timeout_s=2.0):
        """Next packet in arrival order (pending ones first), or None after timeout_s."""
        if self.pending:
            return self.pending.popleft()
        deadline = _now() + timeout_s
        while True:
            p = self._next_frame()
            if p is not None:
                return p
            if _now() >= deadline:
                return None
            _sleep(POLL_S)
            self._fill()

    # ---- public API ---------------------------------------------------------------------

    def flush(self):
        """Drop everything received so far (call before laser_start of a new sequence)."""
        self._fill()
        stale = len(FRAME_RE.findall(self.buffer)) + len(self.pending)
        if stale:
            self.log(logging.WARNING, f"discarded {stale} stale packet(s) before the shot sequence")
        self.buffer = ""
        self.pending.clear()

    def read_shot(self, n, timeout_s=2.5):
        """Packet of shot number n of the current sequence, or None if it does not arrive.

        Older packets (shot < n) are stale and dropped; a newer one (shot > n) means
        shot n is missing: it is kept for the next call, so the following shots stay
        matched to the right packet."""
        deadline = _now() + timeout_s
        while True:
            p = self.read_packet(max(deadline - _now(), 0))
            if p is None:
                self.log(logging.ERROR, f"shot {n}: no timestamp packet within {timeout_s}s")
                return None
            if p.shot < n:
                self.log(logging.WARNING, f"shot {n}: dropped stale packet of shot {p.shot}")
                continue
            if p.shot > n:
                self.pending.appendleft(p)
                self.log(logging.ERROR, f"shot {n}: missing (next packet is shot {p.shot})")
                return None
            return p

    def read_event(self, timeout_s=2.0):
        """Next packet as (seconds, counter_ns, pps_delta_ns, shot); zeros on timeout."""
        p = self.read_packet(timeout_s)
        if p is None:
            return 0, 0, 0, 0
        return p.seconds, p.counter, p.pps_delta, p.shot
