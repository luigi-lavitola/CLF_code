import time
import serial

class FPGAData:
    _instance = None

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
        self.HEADER = 'BAAB'
        self.FOOTER = 'FEEF'
        self.PACKET_SIZE = 40  # Verifica questa lunghezza!
        self.buffer = ""
        self.start_idx =0
        self.end_idx=0

        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.5)
        except serial.SerialException as e:
            raise RuntimeError(f"Errore apertura porta seriale: {e}")

    def read_event(self):
        # Leggi tutto ci� che � disponibile
        #self.buffer += self.serial.read_all().decode('utf-8', 'ignore')
        data=""
        n_try=0
        # Cerca pacchetto completo
        while n_try < 10: 
            self.buffer = self.serial.read_all().decode('utf-8', 'ignore')
            data+= self.buffer
            
            #print(self.buffer)
            #print(len(data),data)
            self.start_idx = data.find(self.HEADER)
            self.end_idx = data.find(self.FOOTER)
            time.sleep(0.2)
            n_try +=1
            if self.start_idx != -1 and self.end_idx !=-1:
                #print(self.start_idx, self.end_idx)
                break

        #print(data,end="")
        #for c in data:
        #    print(c)
        
        packet = data[self.start_idx:self.end_idx + len(self.FOOTER)]
        #print("ok"+packet)# Rimuovi il pacchetto dal buffer
        self.buffer = ""   #self.buffer[end_idx + len(self.FOOTER):]
        return self._parse_packet(packet)


    def _parse_packet(self, packet):
        data = packet[len(self.HEADER):-len(self.FOOTER)]
        try:
            values = data.strip().split('\r')
            if len(values) < 6:
                raise ValueError("Dati incompleti")

            seconds = (int(values[0], 16) << 16) + int(values[1], 16)
            counter = ((int(values[2], 16) << 16) + int(values[3], 16)) * 10
            pps_delta = (int(values[4], 16) - 32767) * 10
            counter_pulses = int(values[5], 16)

            return seconds, counter, pps_delta, counter_pulses
        except Exception as e:
            #print(f"Errore parsing: {e}")
            return 0, 0, 0, 0
