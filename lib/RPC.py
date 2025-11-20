import serial
import re

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

    @check_open
    def wait_prompt(self):
        self.serial.write("\n\r".encode())
        n = 0
        while True:
            for line in self.serial.readlines():
                if line.decode('utf-8','ignore').startswith("RPC>"):
                    return
            n += 1
            if n % 5 == 0:
                self.serial.write("\n\r".encode())

    @check_open
    def on(self):
        for _ in range(5):
            self.serial.reset_output_buffer()
            self.serial.reset_input_buffer()
            self.wait_prompt()
            self.serial.write(f"on {self.id}\r".encode())
            self.serial.flush()
            found = False
            while not found:
                for line in self.serial.readlines():
                    if line.decode('utf-8','ignore').startswith("Turn On"):
                        found = True
                        break
            self.serial.write(b"y\r")  # confirm command 
            if self.status() == 1:
                return True
        print(f"RPC:ON:ERROR:Outlet {self.id} did not turn ON.")
        return False

    @check_open
    def off(self):
        for _ in range(5):
            self.serial.reset_output_buffer()
            self.serial.reset_input_buffer()
            self.wait_prompt()
            self.serial.write(f"off {self.id}\r".encode())
            self.serial.flush()
            found = False
            while not found:
                for line in self.serial.readlines():
                    if line.decode('utf-8','ignore').startswith("Turn Off"):
                        found = True
                        break
            self.serial.write(b"y\r")  # confirm command 
            if self.status() == 0:
                return True
        print(f"RPC:ON:ERROR:Outlet {self.id} did not turn OFF.")
        return False

    @check_open
    def status(self):
        self.wait_prompt()
        self.serial.write(b"\n\r")
        map = {}
        for line in self.serial.readlines():
            match = re.match(r"([1-6])\)\.{3}(.*): (On|Off)", line.decode("utf-8",'ignore'))
            if match:
                map[match.group(1)] = {"device": str.rstrip(match.group(2)), "state": match.group(3)}
        return str.lower(map[str(self.id)]['state']) == 'on'


class RPCOutlet(RPCDevice):

    def __init__(self, serial, id):
        self.serial = serial
        self.id = id

