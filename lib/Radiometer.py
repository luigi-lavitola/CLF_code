import math
import time
import serial
import logging
import datetime
from functools import partial
from logging.handlers import TimedRotatingFileHandler

RADIOMETER_WAIT = 2

_now = time.monotonic      # module level, so that tests can replace the clock

class Radiometer:

    model: str = "unknown"

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1):
        self.port = None
        self.serial = None
        self.ready = False
        self.params = locals()
        self.params.pop('port')
        self.params.pop('self')

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:Unable to create serial device: {e}") 
            raise e

        self.serial.port = port

        self.logger = logging.getLogger("device")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/device.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})


    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            print(f"RPC:CONN: Unable to open device {self.port}: {e}")        

    def is_ready(self):
        return self.ready

    @staticmethod
    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs) 
        return wrapper
    
    # wait for one triggered value at most this long: less than the shot period (1 s),
    # so that a missing value can never be taken from the next shot
    READ_TIMEOUT_S = 0.8

    def _parse_value(self, line):
        """Measured value in a line of the triggered output, None if the line is not a value."""
        raise NotImplementedError

    @check_open
    def read_power(self):
        """Value of the next triggered measurement (10^-3 J); NaN on any error."""
        if not self.ready:
            self.log(logging.ERROR, f"RADM_MON_{self.model}: not ready (setup not done)")
            return math.nan
        deadline = _now() + self.READ_TIMEOUT_S
        saved_timeout = self.serial.timeout
        try:
            while True:
                remaining = deadline - _now()
                if remaining <= 0:
                    self.log(logging.ERROR, f"RADM_MON_{self.model}: no value within {self.READ_TIMEOUT_S}s")
                    return math.nan
                self.serial.timeout = remaining
                self._rx = getattr(self, '_rx', b"") + self.serial.read_until(b"\r")
                if not self._rx.endswith(b"\r"):
                    continue            # timeout in the middle of a line: never parse a cut number
                line, self._rx = self._rx.decode(errors='replace').strip(), b""
                if not line:
                    continue
                value = self._parse_value(line)
                if value is not None:
                    return value
                self.log(logging.WARNING, f"RADM_MON_{self.model}: skipped unexpected line {line!r}")
        except serial.SerialException as e:
            self.log(logging.ERROR, f"RADM_MON_{self.model}: read error: {e}")
            return math.nan
        finally:
            self.serial.timeout = saved_timeout

    @check_open
    def flush_buffers(self):
        self._rx = b""                  # partial line kept by read_power()
        try:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
        except Exception as e:
            print(f"RADM_MON_{self.model}:FLUSH_BUFFERS:Unable to flush buffers")
            return -1

    @check_open
    def set(self, label, value):
        try:
            self.flush_buffers()
            self.serial.write(f"{label} {value}\r".encode())
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to send {label} {value}: {e}")
            return None
        try:
            ret = self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to read result {label} {value}: {e}")
            return None

        if ret[0] != '?':
            return ret[1:]
        else:
            print(f"RADM_MON_{self.model}:SET:Unable to set {label} {value}")
            return None


class Radiometer3700(Radiometer):

    model = "3700"

    def info(self):
        #self.flush_buffers()
        try:
            id = self.get("ID")
            vers = self.get("VR")
            probe = self.get("PA")
            status = self.get("ST")
            if id and vers and probe and status:
                print(f"RADM_MON_{self.model}:RAD_INFO:Radiometer identity: {id}")
                print(f"RADM_MON_{self.model}:RAD_INFO:Radiometer version: {vers}")
                print(f"RADM_MON_{self.model}:RAD_INFO:Probe id and type: {probe}")
                print(f"RADM_MON_{self.model}:RAD_INFO:Status: {status}")
        except Exception as e:
            print(f"RADM_MON_{self.model}:RAD_INFO:ERROR:Some problem occurred: {e}")

    @Radiometer.check_open
    def get(self, label):
        try:
            self.flush_buffers()
            self.serial.write(f"{label}\r".encode())
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:GET:Unable to get {label}: {e}")
            return None
        try:
            ret = self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to read result {label}: {e}")
            return None

        if ret:
            if ret[0] == '?':
                print(f"RADM_MON_{self.model}:GET:Unable to get {label}")
                return None
            else:
                return ret
        return None

    def setup(self):
        try:
            #self.flush_buffers()
            self.set("TG", 3)
            self.set("SS", 0)
            self.set("FA", 1.00)
            self.set("EV", 1)
            self.set("BS", 0)
            self.set("RA", 2)
            self.get("AD")
        except Exception as e:
            #print(f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")
            self.log(logging.ERROR, f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")
            
        self.log(logging.INFO, f"RADM_MON_{self.model}:SET_UP: Radiometer setup completed")
        self.ready = True

    def set_range(self, range):
        self.flush_buffers()
        self.set("RA", range)

    def _parse_value(self, line):
        # triggered output: one plain number per shot
        try:
            return float(line)
        except ValueError:
            return None

class RadiometerOphir(Radiometer):

    model = "OPHIR"

    @Radiometer.check_open
    def get(self, label):
        try:
            self.flush_buffers()
            self.serial.write(f"{label} ?\r".encode())
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:GET:Unable to get {label}: {e}")
            return None
        try:
            ret = self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to read result {label}: {e}")
            return None

        if ret:
            if ret[0] == '?':
                print(f"RADM_MON_{self.model}:GET:Unable to get {label}")
                return None
            elif ret[0] == '*':
                return ret[1:]
        return None

    def info(self):
        self.flush_buffers()
        try: 
            id = self.get("$II")
            probe = self.get("$HI")
            battery = self.get("$BC")

            if id and probe and battery:
                print(f"RADM_{self.model}:RAD_INFO:Radiometer identity: {id}")                
                print(f"RADM_{self.model}:RAD_INFO:Probe id and type: {probe}")
                print(f"RADM_{self.model}:RAD_INFO:Battery conditions: {battery}")
                return 0
            else:
                missing = []
                if not id:
                    missing.append("id")
                if not probe:
                    missing.append("probe")
                if not battery:
                    missing.append("battery")
                print(f"RAD_{self.model}:RAD_INFO:ERROR:Unable to retrieve info: {missing}")
        except Exception as e:
            print(f"RAD_{self.model}:RAD_INFO:ERROR:Some problem occurred: {e}")
            return -1

    def setup(self):
        try:
            self.flush_buffers()
            self.set("$DU", 1)
            self.set("$CS", "1 0 1")
        except Exception as e:
            #print(f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")
            self.log(logging.ERROR, f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")

        #print(f"RADM_MON_{self.model}:SET_UP done")
        self.log(logging.INFO, f"RADM_MON_{self.model}:SET_UP: Radiometer setup completed")
        self.ready = True

    def _parse_value(self, line):
        # triggered output: '*<value>' per shot
        if not line.startswith("*"):
            return None
        try:
            return float(line[1:])
        except ValueError:
            return None
