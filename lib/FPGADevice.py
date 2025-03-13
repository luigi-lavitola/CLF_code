
import serial
import time

class FPGADevice:

    def __init__(self, port, baudrate = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial = None

        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout = 2)
        except serial.SerialException as e:
            raise RuntimeError

        self.regmap = {}
        self.regmap["unixtime"] = FPGARegister(0x0, 2)
        self.regmap["npulses"] = FPGARegister(0x3)

        self.iomap = {}
        self.iomap["norain"] = FPGAIO(0x16, 0)
        self.iomap["rain"] = FPGAIO(0x16, 1)
        self.iomap["cover_closed"] = FPGAIO(0x16, 2, inverted=True)
        self.iomap["cover_open"] = FPGAIO(0x16, 3, inverted=True)
        self.iomap["inverter"] = FPGAIO(0x17, 0)
        self.iomap["flipper1"] = FPGAIO(0x17, 1)
        self.iomap["flipper_raman"] = FPGAIO(0x17, 2)

    def close(self):
        self.serial.close()

    def read_address(self, addr):
        self.serial.write(f"{str(hex(addr))[2:]}\n".encode())
        return int(self.serial.read_until('\r'.encode()).decode()[:-1], 16)

    def write_address(self, addr, value):
        self.serial.write(f"{str(hex(addr))[2:]} {str(hex(value))[2:]}\n".encode())
        time.sleep(0.1)
        self.serial.read_all()

    def read_register(self, name):
        if self.regmap.get(name, None) is None:
            raise NameError
        addr = self.regmap[name].get_addr()
        width = self.regmap[name].get_width()
        i = value = 0
        while i < width:
            value = value | (self.read_address(addr+i) << (i * 16))
            i = i + 1
        return value

    def write_register(self, name, value):
        addr = self.regmap[name].get_addr()
        self.write_address(addr, value)
        
    def read_dio(self, name):
        if self.iomap.get(name, None) is None:
            raise NameError
        addr = self.iomap[name].get_addr()
        bit = self.iomap[name].get_bit()
        inverted = self.iomap[name].get_inverted()
        value = bool(self.read_address(addr) & (1 << bit))
        if inverted:
            return not value
        return value

    def write_dio(self, name, b):
        if self.iomap.get(name, None) is None:
            raise NameError
        addr = self.iomap[name].get_addr()
        bit = self.iomap[name].get_bit()
        value = bool(self.read_address(addr))
        if b:
            value = value | (1 << bit)
        else:
            value = value & ~(1 << bit)
        self.write_address(addr, value)
    
class FPGAIO(FPGADevice):

    def __init__(self, regaddr, bit, inverted=False):
        self.regaddr = regaddr
        self.bit = bit
        self.inverted = inverted

    def get_addr(self):
        return self.regaddr

    def get_bit(self):
        return self.bit

    def get_inverted(self):
        return self.inverted


class FPGARegister(FPGADevice):

    def __init__(self, regaddr, width = 1):
        self.regaddr = regaddr
        self.width = width

    def get_addr(self):
        return self.regaddr

    def get_width(self):
        return self.width
