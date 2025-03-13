import serial

RADIOMETER_WAIT = 2

class Radiometer:

    def __init__(self, port, model, baudrate = 9600):
        self.port = None
        self.serial = None
        self.model = str.upper(model)

        if isinstance(port, str):
            self.port = port
            try:
                self.serial = serial.Serial(port, baudrate, timeout = RADIOMETER_WAIT)
                print(f"RADM_MON_{self.model}:CONN:Connected to {self.port} at {baudrate} baud")
            except serial.SerialException as e:
                print(f"RADM_MON_{self.model}:Unable to reach the device {self.port}: {e}") 
                raise e
        elif isinstance(port, serial.Serial):
            self.serial = port
            self.port = self.serial.port
        else:
            raise TypeError
        
    def flush_buffers(self):
        try:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
        except Exception as e:
            print(f"RADM_MON_{self.model}:FLUSH_BUFFERS:Unable to flush buffers")
            return -1
    
    def set(self, label, value):
        if self.serial and self.serial.is_open:
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
        else:
            print(f"RADM_MON_{self.model}:SET:Serial port is not open")
            return None

    def read_power(self):
        # 10-3 Joule
        None


class Radiometer3700(Radiometer):

    def __init__(self, port, baudrate=9600):
        super().__init__(port, "3700", baudrate)

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

    def get(self, label):
        if self.serial and self.serial.is_open:
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
        else:
            print(f"RADM_MON_{self.model}:SET:Serial port is not open")
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
            print(f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")

    
    def set_range(self, range):
        self.flush_buffers()
        self.set("RA", range)
        

class RadiometerOphir(Radiometer):

    def __init__(self, port, baudrate=9600):
        super().__init__(port, "OPHIR", baudrate)

    def get(self, label):
        if self.serial and self.serial.is_open:
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
        else:
            print(f"RADM_MON_{self.model}:SET:Serial port is not open")
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
        self.flush_buffers()
        self.set("DU", 1)
    

