
import serial
import time
from multiprocessing import Lock

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
        self.mutex = Lock() 

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
        self.regmap["fw_build"] = FPGARegister(0xFC, 2)     # bitstream build time (USR_ACCESS), 0 if absent
        self.regmap["fw_version"] = FPGARegister(0xFF)      # 0 on firmware without the register

        self.iomap = {}
        self.iomap["laser_start"] = FPGAIO(0x3, 0)
        self.iomap["laser_en"] = FPGAIO(0x3, 1)
        self.iomap["timestamp_en"] = FPGAIO(0x3, 2)
        self.iomap["cover_raman_closed"] = FPGAIO(0x16, 0)
        self.iomap["cover_raman_open"] = FPGAIO(0x16, 1)
        self.iomap["cover_steer_closed"] = FPGAIO(0x16, 2, inverted=True)
        self.iomap["cover_steer_open"] = FPGAIO(0x16, 3, inverted=True)
        self.iomap["rain"] = FPGAIO(0x16, 4)
        self.iomap["norain"] = FPGAIO(0x16, 5)
        self.iomap["inverter"] = FPGAIO(0x17, 0)
        self.iomap["flipper_steer"] = FPGAIO(0x17, 1)
        self.iomap["flipper_raman"] = FPGAIO(0x17, 2)
        self.iomap["flipper_atten"] = FPGAIO(0x17, 3)

        self.iomap["pps_ok"] = FPGAIO(0x7, 8)       # PPS_PRESENT (bit 2 is Freq_Back_OK, not driven)
        self.iomap["pps_present"] = FPGAIO(0x7, 8)
        self.iomap["jc_lock"] = FPGAIO(0x8, 2)
        self.iomap["vcxo_lock"] = FPGAIO(0x8, 3)
        self.iomap["force_align"] = FPGAIO(0x9, 4)
        self.iomap["pll30_lock"] = FPGAIO(0x8, 4)     # hw v2: clk_wiz 30.72 -> 122.88 MHz locked
        self.iomap["gps_run"] = FPGAIO(0x26, 0)       # hw v2: GPS_RESET pin (active low), 0 = GPS in reset

    def close(self):
        self.serial.close()

    def apply_dio_map(self, overrides):
        """Site wiring of the DB25 digital I/O: {name: [register, bit, inverted]}."""
        for name, (regaddr, bit, inverted) in overrides.items():
            if name not in self.iomap:
                raise NameError(f"dio.yml: unknown FPGA I/O '{name}'")
            self.iomap[name] = FPGAIO(int(regaddr), int(bit), inverted=bool(inverted))

    # one register access takes well under a second: a lock held longer means the holder is stuck
    LOCK_TIMEOUT_S = 10
    READ_RETRIES = 3

    def critical_section(func):
        def wrapper(self, *args, **kwargs):
            mutex = self.mutex          # local: RunManager may replace a lock left held by a dead process
            if not mutex.acquire(timeout=self.LOCK_TIMEOUT_S):
                raise TimeoutError(f"FPGA serial lock not released within {self.LOCK_TIMEOUT_S}s")
            try:
                return func(self, *args, **kwargs)
            finally:
                mutex.release()         # also on exceptions
        return wrapper

    @critical_section
    def read_address(self, addr):
        """Register value; IOError after READ_RETRIES missing/malformed answers.

        (It used to return 0 silently, and write_dio() then wrote that 0 back, clearing
        the other bits of the register.)"""
        for _ in range(self.READ_RETRIES):
            self.serial.reset_input_buffer()            # drop a late answer to an earlier request
            self.serial.write(f"{str(hex(addr))[2:]}\n".encode())
            answer = self.serial.read_until('\r'.encode())
            if not answer.endswith(b'\r'):
                continue                                # timeout: never parse a partial answer
            try:
                return int(answer[:-1].decode(errors='replace').strip(), 16)
            except ValueError:
                continue
        raise IOError(f"FPGA: no valid answer reading address {hex(addr)} ({self.READ_RETRIES} attempts)")

    @critical_section
    def write_address(self, addr, value):
        self.serial.write(f"{str(hex(addr))[2:]} {str(hex(value))[2:]}\n".encode())
        time.sleep(0.1)
        self.serial.read_all()

    def read_register(self, name):
        if self.regmap.get(name, None) is None:
            raise NameError
        addr = self.regmap[name].get_addr()
        width = self.regmap[name].get_width()
        if name == "time_cnt":
            # 0x0D = Time_Tag[15:0] (reading it latches 0x0E), 0x0E = Time_Tag[26:11], not [31:16]
            lo = self.read_address(addr)
            hi = self.read_address(addr + 1)
            return (hi << 11) | (lo & 0x7FF)
        i = value = 0
        while i < width:
            value = value | (self.read_address(addr+i) << (i * 16))
            i = i + 1
        return value

    def write_register(self, name, value):
        addr = self.regmap[name].get_addr()
        width = self.regmap[name].get_width()
        i = 0
        while i < width:
            self.write_address(addr+i, (value & (0xFFFF << (i*16))) >> (i*16))
            i = i + 1

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
        value = self.read_address(addr)
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
