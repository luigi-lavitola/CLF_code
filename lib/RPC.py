import serial
import time
import re

# Costanti
RPC_RETURN = 255

class RPCDevice:

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1):
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

    def add_outlet(self, id, name):
        self.outlets[name] = self.RPCOutlet(self.serial, id)
        return self.outlets[name]

    def get_outlet(self, name):
        return self.outlets[name]


    class RPCOutlet:

        def __init__(self, serial, id):
            self.serial = serial
            self.id = id

        def check_open(func):
            def wrapper(self, *args, **kwargs):
                if self.serial.is_open is False:
                    self.serial.open()
                return func(self, *args, **kwargs)
            return wrapper
    
        @check_open
        def send_command(self, command):
            self.serial.flush()
            self.serial.write(f"{command}\r".encode())
            self.serial.read_until()
            self.serial.write(b"y\r")  # confirm command 
            self.serial.read_until()

        @check_open
        def read_response(self):
            response = self.serial.read(RPC_RETURN).decode(errors='ignore').strip()
            return response

        @check_open
        def on(self):
            self.serial.flush()
            self.send_command(f"on {self.id}")
            if self.status() == 1:
                return True
            print(f"RPC:ON:ERROR:Outlet {self.id} did not turn ON.")
            return False

        @check_open
        def off(self):
            self.serial.flush()
            self.send_command(f"off {self.id}")
            if self.status() == 0:
                return True
            print(f"RPC:OFF:ERROR:Outlet {self.id} did not turn OFF.")
            return False

        @check_open
        def status(self):
            self.serial.flush()
            self.serial.write(b"\r")
            map = {}
            for line in self.serial.readlines():
                match = re.match(r"([1-6])\)\.{3}(.*): (On|Off)", line.decode("utf-8"))
                if match:
                    map[match.group(1)] = {"device": str.rstrip(match.group(2)), "state": match.group(3)}
            return str.lower(map[str(self.id)]['state']) == 'on'
