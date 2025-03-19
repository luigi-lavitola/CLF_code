import serial

RADIOMETER_WAIT = 2

class Radiometer:

    def __init__(self, port, model, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1):
        self.port = None
        self.serial = None
        self.model = str.upper(model)
        self.ready = False
        self.params = locals()
        self.params.pop('port')
        self.params.pop('model')
        self.params.pop('self')

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:Unable to create serial device: {e}") 
            raise e

        self.serial.port = port

    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            rint(f"RPC:CONN: Unable to open device {self.port}: {e}")        

    def is_ready(self):
        return self.ready

    @staticmethod
    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs) 
        return wrapper
    
    @check_open
    def flush_buffers(self):
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

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1):
        self.params = locals()
        self.params.pop('self')
        self.params.pop('__class__')
        super().__init__(model='3700', **self.params)

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
            print(f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")

        print(f"RADM_MON_{self.model}:SET_UP done")
        self.ready = True

    def set_range(self, range):
        self.flush_buffers()
        self.set("RA", range)

    def read_power(self):
        if (self.ready == True):
            # 10-3 Joule unit
            return self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        else:
            print(f"RADM_MON_{self.model}:ERROR Radiometer not ready")

class RadiometerOphir(Radiometer):

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1):
        self.params = locals()
        self.params.pop('self')
        self.params.pop('__class__')
        super().__init__(model="OPHIR", **self.params)

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
        self.flush_buffers()
        self.set("DU", 1)
    

