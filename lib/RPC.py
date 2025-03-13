import serial
import time

# Costanti
RPC_RETURN = 255
RPC_WAIT = 1  # Timeout in secondi

# Stati degli outlet
RPC_BREAKER = 0
RPC_RAMAN = 1
RPC_RAD = 2
RPC_LSR = 3
RPC_RCOVER = 4
RPC_VCOVER = 5
RPC_VXM = 6

class RPCDevice:

    def __init__(self, port, baudrate=9600):
        self.outlets = {}
        self.port = None
        self.serial = None

        if isinstance(port, str):
            self.port = port
            try:
                self.serial = serial.Serial(self.port, baudrate, timeout=RPC_WAIT)
                print(f"RPC:CONN: Connected to {self.port} at {baudrate} baud.")
            except serial.SerialException as e:
                print(f"RPC:CONN: Unable to open device {self.port}: {e}")
        elif isinstance(port, serial.Serial):
            self.serial = port
            self.port = self.serial.port
        else:
            raise TypeError

    def add_outlet(self, id, name):
        self.outlets[name] = self.RPCOutlet(self.serial, id)
        return self.outlets[name]

    def get_outlet(self, name):
        return self.outlets[name]


    class RPCOutlet:

        def __init__(self, serial, id):
            self.state = [-1] * 7  # Stato iniziale sconosciuto
            self.serial = serial
            self.id = id

        def send_command(self, command):
            if self.serial and self.serial.is_open:
                self.serial.flushInput()
                self.serial.write(f"{command}\r".encode())
                time.sleep(0.5)
                self.serial.write(b"y\r")  # Conferma comando
                time.sleep(0.3)
            else:
                print("RPC:SEND_COMM:Serial port is not open.")

        def read_response(self):
            if self.serial and self.serial.is_open:
                response = self.serial.read(RPC_RETURN).decode(errors='ignore').strip()
                return response
            return ""

        def on(self):
            for _ in range(3):
                self.send_command(f"on {self.id}")
            if self.status() == 1:
                return 1
            for _ in range(4):
                self.send_command(f"on {self.id}")
            if self.status() == 1:
                return 1
            print(f"RPC:ON:ERROR:Outlet {self.id} did not turn ON.")
            return 0

        def off(self):
            for _ in range(3):
                self.send_command(f"off {self.id}")
            if self.status() == 0:
                return 0
            for _ in range(4):
                self.send_command(f"off {self.id}")
            if self.status() == 0:
                return 0
            print(f"RPC:OFF:ERROR:Outlet {self.id} did not turn OFF.")
            return 1

        def status(self):
            self.serial.flushInput()
            self.serial.write(b"\r")
            time.sleep(0.05)
            if self.id >= 0 and self.id <= 6:
                return self.state[self.id]
            elif self.id == 0:
                return sum(1 for s in self.state if s == 1)
            else:
                return -1
    #     def status(self):
    #         self.serial.flushInput()
    #         self.serial.write(b"\r")
    #         time.sleep(0.05)

    #         response = self.read_response()
    #         if "Circuit Breaker: Off" in response:
    #             self.state[RPC_BREAKER] = 0
    #             return -2
    #         if "Circuit Breaker: On" in response:
    #             self.state[RPC_BREAKER] = 1

    #         outlet_status = {
    #             "1)...ramansys  : On": RPC_RAMAN,
    #             "2)...rad (mon) : On": RPC_RAD,
    #             "3)...laser     : On": RPC_LSR,
    #             "4)...rmotor    : On": RPC_RCOVER,
    #             "5)...Vcover    : On": RPC_VCOVER,
    #             "6)...vxm       : On": RPC_VXM
    #         }

    #         outlet_off_status = {
    #             "1)...ramansys  : Off": RPC_RAMAN,
    #             "2)...rad (mon) : Off": RPC_RAD,
    #             "3)...laser     : Off": RPC_LSR,
    #             "4)...rmotor    : Off": RPC_RCOVER,
    #             "5)...Vcover    : Off": RPC_VCOVER,
    #             "6)...vxm       : Off": RPC_VXM
    #         }

    #         for line in response.split('\n'):                
    #             for key, val in outlet_status.items():
    #                 if key in line:
    #                     self.state[val] = 1
    #             for key, val in outlet_off_status.items():
    #                 if key in line:
    #                     self.state[val] = 0
    # def on(self, outlet):
    #     for _ in range(3):
    #         self.send_command(f"on {outlet}")
    #     if self.status(outlet) == 1:
    #         return 1
    #     for _ in range(4):
    #         self.send_command(f"on {outlet}")
    #     if self.status(outlet) == 1:
    #         return 1
    #     print(f"RPC:ON:ERROR:Outlet {outlet} did not turn ON.")
    #     return 0

    # def off(self, outlet):
    #     for _ in range(3):
    #         self.send_command(f"off {outlet}")
    #     if self.status(outlet) == 0:
    #         return 0
    #     for _ in range(4):
    #         self.send_command(f"off {outlet}")
    #     if self.status(outlet) == 0:
    #         return 0
    #     print(f"RPC:OFF:ERROR:Outlet {outlet} did not turn OFF.")
    #     return 1

    

if __name__ == "__main__":
    # usage with serial object as parameter
    #s = serial.Serial('/dev/ttyUSB0')
    #rpc = RPCDevice(s)

    rpc = RPCDevice('/dev/ttyUSB0')  # Modifica la porta se necessario

    o1 = rpc.add_outlet(0, "RAMAN1")
    o1.on()
    o1.off()
    o1.status()
    
    rpc.add_outlet(1, "PC")
    o2 = rpc.get_outlet("PC")
    o2.on()
    o2.status()

    #outlet = 1  # Cambia l'outlet da controllare
    #print(f"Accensione outlet {outlet}:", rpc.on(outlet))
    #print(f"Stato outlet {outlet}:", rpc.status(outlet))
    #print(f"Spegnimento outlet {outlet}:", rpc.off(outlet))
    #print(f"Stato outlet {outlet}:", rpc.status(outlet))
