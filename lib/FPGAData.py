import serial
import time

class FPGAData:

    __instance = None

    @staticmethod
    def getInstance():
        if FPGAData.__instance == None:
            raise Exception("Class FPGAData - no instance")
        return FPGAData.__instance

    def __init__(self, port, baudrate = 115200):
        if FPGAData.__instance != None:
            raise Exception("Class FPGAData - use existing instance")
        else:
            FPGAData.__instance = self

        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.HEADER = 'BAAB'
        self.FOOTER = 'FEEF'
        self.PACKET_SIZE = 40  # 4 byte di header + 12 byte di dati + 4 byte di footer

        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout = 2)
        except serial.SerialException as e:
            raise RuntimeError

    def read_event(self):
        
            self.buffer = self.serial.read(self.PACKET_SIZE)  # Legge il pacchetto intero
            
            # Cerca l'header
            start_idx = self.buffer.find(self.HEADER.encode())
            if start_idx != -1 and len(self.buffer) >= start_idx + self.PACKET_SIZE:
                packet = self.buffer[start_idx:start_idx + self.PACKET_SIZE]

                if packet[-5:-1] == self.FOOTER.encode():
                    data = packet[5:-5]
                    try:
                        values = data.decode().split('\r')[:-1]
                        self.seconds = (int(values[0], 16) << 16) + int(values[1], 16)
                        self.counter = (int(values[2], 16) << 16) + int(values[3], 16) * 10
                        self.length = (int(values[4], 16) << 16) + int(values[5], 16) * 10
                        return self.seconds, self.counter, self.length
                    except (IndexError, ValueError, UnicodeDecodeError) as e:
                        print("Errore nel parsing dei dati:", e)
                else:
                    print("Errore: pacchetto non valido!")

            # Se il pacchetto non è valido o non è stato trovato
            self.seconds = 0
            self.counter = 0
            self.length = 0
            return self.seconds, self.counter, self.length