"""
Alignment of the FPGA seconds counter (UNIX time) to the host clock.

Firmware behaviour (Time_Tag_Gen / Run_Control):
- writing 'arm_unixtime' (0x19 low word, then 0x1A high word) loads the value into the
  seconds counter immediately, not at the next PPS; the load happens only if the value
  differs from the previous one written
- the counter then increments at every local PPS

So the value of the *current* second is written just after a second boundary (each
register write takes ~0.1 s) and the result is verified after the next PPS, at mid-second.
The host clock must be UTC and accurate well within WRITE_AT (NTP/gpsd).
"""

import math
import time

WRITE_AT = 0.15     # s after the second boundary: write the current second
CHECK_AT = 0.5      # s after the second boundary: compare FPGA and host seconds


def _clock(now, sleep):
    # resolved at call time, so that time.time / time.sleep can be replaced (tests)
    return (now or time.time), (sleep or time.sleep)


def _wait_fraction(frac, now, sleep):
    """Sleep until `frac` seconds after the next suitable second boundary."""
    t = now()
    target = math.floor(t) + frac
    if t >= target:
        target += 1
    sleep(target - t)


def offset(fpga, now=None, sleep=None, after_next_pps=False):
    """FPGA seconds - host seconds, sampled at mid-second (0 = aligned).

    after_next_pps: sample in the *next* second, so that at least one PPS has
    incremented the counter (right after a write, the same second would just
    read back the written value, even with no PPS)."""
    now, sleep = _clock(now, sleep)
    _wait_fraction(CHECK_AT, now, sleep)
    if after_next_pps:
        _wait_fraction(CHECK_AT, now, sleep)
    host = int(now())
    return fpga.read_register('unixtime') - host


def align(fpga, now=None, sleep=None):
    """Load the current host second into the FPGA counter (no verification)."""
    now, sleep = _clock(now, sleep)
    _wait_fraction(WRITE_AT, now, sleep)
    fpga.write_register('arm_unixtime', int(now()))


PPS_LIMIT_NS = 100          # same limit as the gps_ns_error alarm in sensors.yml
PPS_SETTLE_S = 2.5          # force align acts at the next GPS PPS; the error is measured at the one after


def pps_error_ns(fpga, tick_ns):
    """GPS PPS - local PPS measured by the FPGA (pps_distance, zero 32767 as in the logs)."""
    return (fpga.read_register('pps_distance') - 32767) * tick_ns


def ensure_pps(fpga, tick_ns, log, limit_ns=PPS_LIMIT_NS, sleep=None):
    """Align the local PPS (FPGA sub-second counter) to the GPS PPS when it is off.

    On hw v1 the VCXO PID keeps it aligned; on hw v2 (LEA-M8F clock, no PID on the clock)
    the local PPS has an arbitrary phase after power-up and only a force align fixes it:
    without it the shots would be at an arbitrary time with respect to the GPS second.
    Do it BEFORE ensure(): the forced local PPS also increments the seconds counter.
    Never raises: returns True when the error is within limit_ns."""
    _, sleep = _clock(None, sleep)
    try:
        err = pps_error_ns(fpga, tick_ns)
        if abs(err) <= limit_ns:
            log('info', f"local PPS aligned with GPS ({err:+.0f} ns)")
            return True
        log('warning', f"local PPS off by {err:+.0f} ns from GPS: force align")
        fpga.write_dio('force_align', True)         # firmware clears the bit by itself
        sleep(PPS_SETTLE_S)
        err = pps_error_ns(fpga, tick_ns)
        if abs(err) <= limit_ns:
            log('info', f"local PPS aligned with GPS after force align ({err:+.0f} ns)")
            return True
        log('error', f"local PPS still off by {err:+.0f} ns after force align (GPS PPS missing?)")
        return False
    except Exception as e:
        log('error', f"local PPS check failed: {e!r}")
        return False


def ensure(fpga, log, attempts=3, now=None, sleep=None):
    """Check the FPGA counter and align it if needed. True when verified aligned.

    log(level_name, message) is called with 'info' / 'warning' / 'error'."""
    try:
        return _ensure(fpga, log, attempts, now, sleep)
    except Exception as e:          # FPGA not answering: report, never stop the caller
        log('error', f"FPGA seconds counter check failed: {e!r}")
        return False


def _ensure(fpga, log, attempts, now, sleep):
    off = offset(fpga, now, sleep)
    if off == 0:
        log('info', "FPGA seconds counter aligned with host clock")
        return True
    log('warning', f"FPGA seconds counter off by {off} s: aligning")
    for i in range(attempts):
        align(fpga, now, sleep)
        off = offset(fpga, now, sleep, after_next_pps=True)
        if off == 0:
            log('info', f"FPGA seconds counter aligned (attempt {i + 1})")
            return True
    log('error', f"FPGA seconds counter still off by {off} s after {attempts} attempts "
                 "(no PPS? host clock not synchronised?)")
    return False
