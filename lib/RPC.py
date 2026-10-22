import serial
import re
import time
import logging
from functools import partial

# Baytech RPC (owner's manual): pressing Enter prints the status menu followed by the
# "RPC>" prompt; "ON n" / "OFF n" asks "Turn On Outlet n (Y/N)?", and after "Y" the
# updated status menu and the prompt are printed again.
#
# Waits are blocking by design: an outlet must never be left in an unknown state, so
# the code keeps waiting for the RPC (logging a warning every WAIT_WARNING_S).

POLL_S = 0.05
WAIT_WARNING_S = 60
PROMPT_RE = re.compile(r"RPC\s?>")
OUTLET_RE = re.compile(r"([1-8])\)\s*(?:\.\s*){3}(.*?)\s*:\s*(On|Off)")

_now = time.monotonic       # module level, so that tests can replace the clock
_sleep = time.sleep

_log = partial(logging.getLogger("device").log, extra={'classname': 'RPC'})


def parse_status(output):
    """{outlet number: {"device": name, "state": "On"/"Off"}} from a status menu."""
    status = {}
    for line in output.splitlines():
        match = OUTLET_RE.search(line)
        if match:
            status[match.group(1)] = {"device": match.group(2).rstrip(), "state": match.group(3)}
    return status


class RPCDevice:

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2):
        self.outlets = {}
        self.port = port
        self.serial = None
        self.params = locals()
        self.params.pop('port')
        self.params.pop('self')

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
            print(f"RPC:CONN: Unable to create serial device: {e}")

        self.serial.port = port

    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            print(f"RPC:CONN: Unable to open device {self.port}: {e}")

    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs)
        return wrapper

    def add_outlet(self, id, name):
        self.outlets[name] = RPCOutlet(self.serial, id)
        return self.outlets[name]

    def get_outlet(self, name):
        return self.outlets[name]

    def _read_until(self, done, what):
        """Accumulate the RPC output until done(output) is true. Never gives up (see top),
        but logs a warning every WAIT_WARNING_S and does not busy-wait."""
        output = ""
        start = _now()
        next_warning = start + WAIT_WARNING_S
        while True:
            output += self.serial.read_all().decode('utf-8', 'ignore')
            if done(output):
                return output
            t = _now()
            if t >= next_warning:
                _log(logging.WARNING, f"RPC: still waiting for {what} after {t - start:.0f}s "
                                      f"(last output {output[-80:]!r})")
                next_warning += WAIT_WARNING_S
            _sleep(POLL_S)

    @check_open
    def wait_prompt(self):
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.serial.write('\r\n'.encode('utf-8'))
        self.serial.flush()
        output = self._read_until(lambda o: PROMPT_RE.search(o), "prompt")
        _sleep(0.2)
        return output

    @check_open
    def status(self):
        output = self.wait_prompt()
        return str.lower(parse_status(output)[str(self.id)]['state']) == 'on'

    def set(self, id, state):
        cmd = ["off", "on"]

        self.wait_prompt()
        self.serial.write(f"{cmd[state]} {id}\r\n".encode())
        self.serial.flush()
        while True:
            output = self._read_until(lambda o: "(Y/N)?" in o or "ERROR" in o, f"confirmation of {cmd[state]} {id}")
            if "(Y/N)?" in output:
                break
            # ERROR: get a fresh prompt and send the command again
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            self.serial.flush()
            self.wait_prompt()
            self.serial.write(f"{cmd[state]} {id}\r\n".encode())
            self.serial.flush()

        self.serial.write(b"y\r\n")  # confirm command
        self.serial.flush()

        # the prompt comes back once the command has been executed; the updated status menu
        # is normally printed with it (manual), otherwise ask for it with an Enter.
        # (The old code asked for the status at once and could see the outlet before it switched.)
        output = self._read_until(lambda o: PROMPT_RE.search(o), f"prompt after {cmd[state]} {id}")
        status = parse_status(output)
        if str(id) not in status:
            status = parse_status(self.wait_prompt())
        return (str.lower(status[str(id)]['state']) == 'on') == bool(state)

    @check_open
    def on(self):
        return self.set(self.id, 1)

    @check_open
    def off(self):
        return self.set(self.id, 0)

class RPCOutlet(RPCDevice):

    def __init__(self, serial, id):
        self.serial = serial
        self.id = id
