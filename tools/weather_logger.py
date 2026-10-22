#!/usr/bin/env python3
"""
Weather station logger (replaces spikes/weather_log.py), run as the clf-weather service.

Every INTERVAL_S seconds, aligned to the clock (:00, :05, ...), reads one record from the
weather station and appends it to logs/weather_log.csv (same columns as before) and to
logs/weather.log.

Serial port: 'weather_Station' in conf/<identity>/ports.yml (identity from
conf/parameters.yml), or --port / --baudrate.

Station dialogue (as in the original spike): "G" then "1B", then "1D" answers with an echo
line and two data lines. Each field is "<index><sign><value>", e.g. "05+0012.3" or
"05-0003.1" (negative). Field order: code, year, day, hhmm, temperature, humidity,
current / average / max wind speed, ..., pressure (last).
"""

import argparse
import csv
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

import serial
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")
CSV_FILE = os.path.join(LOG_DIR, "weather_log.csv")
LOG_FILE = os.path.join(LOG_DIR, "weather.log")

INTERVAL_S = 300
STEP_S = 0.2                 # pause after each command, as in the original spike
MIN_FIELDS = 10              # code ... maxwspeed + pressure

CSV_HEADER = ["timestamp", "code", "year", "day", "hour", "minute",
              "temperature", "humidity", "curwspeed", "avgwspeed", "maxwspeed", "pressure"]

# "<index>+<value>" / "<index>-<value>"; value may end with '.' (e.g. "02+2026.")
FIELD_RE = re.compile(r"^\d+([+-]\d*\.?\d*)$")

log = logging.getLogger("weather")


def configure_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fmt.converter = time.gmtime                      # UTC timestamps
    fh = TimedRotatingFileHandler(LOG_FILE, when="midnight", utc=True, backupCount=14, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler()                     # -> journal when run by systemd
    sh.setFormatter(fmt)
    log.addHandler(sh)


def port_from_config():
    """Serial parameters of 'weather_Station' for the site in conf/parameters.yml."""
    with open(os.path.join(ROOT, "conf", "parameters.yml")) as f:
        params = {k: v for doc in yaml.safe_load_all(f) for k, v in doc.items()}
    identity = str.lower(params["identity"])
    with open(os.path.join(ROOT, "conf", identity, "ports.yml")) as f:
        ports = {k: v for doc in yaml.safe_load_all(f) for k, v in doc.items()}
    p = ports["weather_Station"]
    return dict(port=p["port"], baudrate=p.get("baudrate", 9600), timeout=p.get("timeout", 1))


def parse_fields(raw):
    """Signed values of the fields of a record; ValueError if a field is not '<index>[+-]<value>'."""
    values = []
    for token in raw.split():
        m = FIELD_RE.match(token)
        if not m or m.group(1) in ("+", "-"):
            raise ValueError(f"unexpected field {token!r}")
        values.append(float(m.group(1)))
    if len(values) < MIN_FIELDS:
        raise ValueError(f"{len(values)} fields, at least {MIN_FIELDS} expected")
    return values


def to_record(values):
    hhmm = int(values[3])
    return {
        "code": values[0], "year": values[1], "day": values[2],
        "hour": hhmm // 100, "minute": hhmm % 100,
        "temperature": values[4], "humidity": values[5],
        "curwspeed": values[6], "avgwspeed": values[7], "maxwspeed": values[8],
        "pressure": values[-1],
    }


def _command(s, text):
    s.write(f"{text}\r\n".encode())
    time.sleep(STEP_S)


def read_station(port, baudrate=9600, timeout=1):
    """One raw record from the station ('' lines if it does not answer within the timeouts)."""
    with serial.Serial(port, baudrate, timeout=timeout) as s:   # timeout: never block forever
        _command(s, "")
        _command(s, "")
        s.read_all()
        _command(s, "G")
        s.read_all()
        _command(s, "1B")
        s.read_all()
        _command(s, "1D")
        s.read_until(b"\n")                                      # echo of the command
        line1 = s.read_until(b"\n").decode(errors="replace").strip()
        line2 = s.read_until(b"\n").decode(errors="replace").strip()
    return f"{line1} {line2}".strip()


def prepare_csv():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.isfile(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADER)


def save_csv(record, when):
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([when.strftime("%Y-%m-%dT%H:%M:%S")] + [record[k] for k in CSV_HEADER[1:]])


def read_and_log(port_params):
    when = datetime.now(timezone.utc)
    raw = read_station(**port_params)
    try:
        record = to_record(parse_fields(raw))
    except ValueError as e:
        log.error("unreadable record (%s): %r", e, raw)
        return False
    log.info("T=%.2f C RH=%.2f %% P=%.1f hPa wind cur=%.2f avg=%.2f max=%.2f",
             record["temperature"], record["humidity"], record["pressure"],
             record["curwspeed"], record["avgwspeed"], record["maxwspeed"])
    save_csv(record, when)
    return True


def sleep_to_next(interval_s):
    time.sleep(interval_s - time.time() % interval_s)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weather station logger")
    ap.add_argument("--port", help="serial port (default: weather_Station in ports.yml)")
    ap.add_argument("--baudrate", type=int, default=None)
    ap.add_argument("--interval", type=int, default=INTERVAL_S, help="seconds between readings")
    ap.add_argument("--once", action="store_true", help="one reading, printed, then exit")
    args = ap.parse_args(argv)

    configure_logging()
    port_params = port_from_config() if args.port is None else dict(port=args.port, baudrate=9600, timeout=1)
    if args.baudrate:
        port_params["baudrate"] = args.baudrate

    if args.once:
        raw = read_station(**port_params)
        print("raw:", repr(raw))
        print(to_record(parse_fields(raw)))
        return

    prepare_csv()
    log.info("weather logging started on %s, every %d s", port_params["port"], args.interval)
    failures = 0
    while True:
        sleep_to_next(args.interval)
        try:
            ok = read_and_log(port_params)
        except Exception as e:                       # serial errors, port missing, ...
            log.error("weather station read failed: %r", e)
            ok = False
        failures = 0 if ok else failures + 1
        if failures in (3, 12, 288):                 # 15 min, 1 h, 1 day without data
            log.warning("no weather data for %d readings", failures)


if __name__ == "__main__":
    sys.exit(main())
