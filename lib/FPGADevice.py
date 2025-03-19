
import serial
import time

class FPGADevice:

    __instance = None

    @staticmethod
    def getInstance():
        if FPGADevice.__instance == None:
            raise Exception("Class FPGADevice - no instance")
        return FPGADevice.__instance

    def __init__(self, port, baudrate = 115200):
        if FPGADevice.__instance != None:
            raise Exception("Class FPGADevice - use existing instance")
        else:
            FPGADevice.__instance = self

        self.port = port
        self.baudrate = baudrate
        self.serial = None

        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout = 2)
        except serial.SerialException as e:
            raise RuntimeError

        self.regmap = {}
        self.regmap["unixtime"] = FPGARegister(0x0, 2)
        self.regmap["pps_delay"] = FPGARegister(0x5, 2)
        self.regmap["pps_distance"] = FPGARegister(0xB)
        self.regmap["pid_value"] = FPGARegister(0xC)
        self.regmap["time_cnt"] = FPGARegister(0xD, 2)
        self.regmap["vcxo_value"] = FPGARegister(0xF)
        self.regmap["pid_dac"] = FPGARegister(0x10)
        self.regmap["pid_dac_p"] = FPGARegister(0x11)
        self.regmap["pid_dac_i"] = FPGARegister(0x12)
        self.regmap["pulse_width"] = FPGARegister(0x13)
        self.regmap["pulse_energy"] = FPGARegister(0x14, 2)
        self.regmap["arm_unixtime"] = FPGARegister(0x19, 2)
        self.regmap["pulse_period"] = FPGARegister(0x1B, 2)
        self.regmap["mux_bnc_0"] = FPGARegister(0x1D)
        self.regmap["mux_bnc_1"] = FPGARegister(0x1E)
        self.regmap["mux_bnc_2"] = FPGARegister(0x1F)
        self.regmap["mux_bnc_3"] = FPGARegister(0x20)
        self.regmap["mux_bnc_4"] = FPGARegister(0x21)
        self.regmap["shots_num"] = FPGARegister(0x22, 2)
        self.regmap["shots_cnt"] = FPGARegister(0x24, 2)

        self.iomap = {}
        self.iomap["laser_start"] = FPGAIO(0x3, 0)
        self.iomap["laser_en"] = FPGAIO(0x3, 1)
        self.iomap["norain"] = FPGAIO(0x16, 0)
        self.iomap["rain"] = FPGAIO(0x16, 1)
        self.iomap["cover_closed"] = FPGAIO(0x16, 2, inverted=True)
        self.iomap["cover_open"] = FPGAIO(0x16, 3, inverted=True)
        self.iomap["inverter"] = FPGAIO(0x17, 0)
        self.iomap["flipper_steer"] = FPGAIO(0x17, 1)
        self.iomap["flipper_raman"] = FPGAIO(0x17, 2)
        self.iomap["flipper_atten"] = FPGAIO(0x17, 3)

        self.iomap["pps_ok"] = FPGAIO(0x7, 2)
        self.iomap["jc_lock"] = FPGAIO(0x8, 2)
        self.iomap["vcxo_lock"] = FPGAIO(0x8, 3)
        self.iomap["force_align"] = FPGAIO(0x9, 4)

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

    def read_bit(self, name):
        return self.read_dio(name) 

    def write_bit(self, name, b):
        self.write_dio(name, b)

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
