
from time import sleep
from enum import Enum
from functools import reduce
from pyftdi.spi import SpiController
from lib.LTC2983_const import *

class LTC2983_Base:

   class Register:
      COMMAND_STATUS = 0x0000
      GLOBAL_CONFIGURATION = 0x00F0
      MUX_DELAY = 0x00FF

   def __init__(self):
      # temperature in Celsius, rejection 50Hz/60Hz
      self.write_register(self.Register.GLOBAL_CONFIGURATION, 
         REJECTION__50_60_HZ | TEMP_UNIT__C)
      # set mux delay to 0
      self.write_register(self.Register.MUX_DELAY, 0x00)

   def config_channel(self, ch, data):
      addr = 0x200 + (4 * (ch - 1))
      self.write_register(addr, data, 4)

   # a conversion takes a few hundred ms (50/60 Hz rejection): give up well after that,
   # so that a dead converter raises instead of blocking the housekeeping thread forever
   CONVERSION_TIMEOUT_S = 2.0
   POLL_S = 0.05

   # result register: bits 31..24 = fault byte, bits 23..0 = temperature (two's complement, 1/1024 C)
   FAULT_VALID = 0x01                  # bit 24: result valid
   FAULT_HARD = 0x80 | 0x40            # bit 31 sensor hard fault, bit 30 hard ADC out of range

   def read_channel(self, ch):
      self.write_register(self.Register.COMMAND_STATUS, (0x80 | ch))
      for _ in range(int(self.CONVERSION_TIMEOUT_S / self.POLL_S)):
         if self.read_register(self.Register.COMMAND_STATUS) & 0x40:
            break
         sleep(self.POLL_S)
      else:
         raise TimeoutError(f"LTC2983: conversion of channel {ch} not done within {self.CONVERSION_TIMEOUT_S}s")
      value = self.read_register(READ_CH_BASE + (4 * (ch - 1)), 4)

      return value

   def read_temperature(self, ch):
      """Temperature in C, NaN when the converter flags the result as invalid (open/shorted sensor)."""
      raw = self.read_channel(ch)
      fault = raw >> 24
      if not (fault & self.FAULT_VALID) or (fault & self.FAULT_HARD):
         return float('nan')
      return self.signed_to_temperature(self.raw_to_signed(raw))

   def raw_to_signed(self, value):
      # 24-bit two's complement -> Python int (negative below 0 C)
      x = value & 0x00FFFFFF
      if x & 0x00800000:
         x -= 1 << 24

      return x

   def signed_to_temperature(self, value):
      return value / 1024.0

   def dump_registers(self):
      print(f'COMMAND_STATUS addr: 0x0000, value: {hex(self.read_register(self.Register.COMMAND_STATUS))}')
      print(f'GLOBAL_CONFIGURATION addr: 0x0000, value: {hex(self.read_register(self.Register.GLOBAL_CONFIGURATION))}')
      print(f'MUX_DELAY addr: 0x0000, value: {hex(self.read_register(self.Register.MUX_DELAY))}')
   
class LTC2983_FTDI(LTC2983_Base):

   def __init__(self, slave):
      self.spi = slave
      super().__init__()

   def read_register(self, addr, nbytes=1):
      l = list(self.spi.exchange([RD_REG, ((addr & 0xFF00) >> 8), (addr & 0xFF)], nbytes))
      return reduce(lambda x, y: x * 0x100 + y, l)

   def write_register(self, addr, value, nbytes=1):
      l = [WR_REG, ((addr & 0xFF00) >> 8), (addr & 0xFF)]
      l.extend(value.to_bytes(nbytes, 'big'))     # explicit byteorder: required before Python 3.11
      self.spi.write(l)

class LTC2983(LTC2983_Base):

   def __init__(self):
      None

   def get_ftdi_backend(self, slave):
      return LTC2983_FTDI(slave) 
