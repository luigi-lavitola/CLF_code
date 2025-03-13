#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.FPGADevice import FPGADevice

fp = FPGADevice("/dev/runcontrol")

print("1. dump FPGA registers (0-30)")
for reg in range(0,30):
   print(f'{reg} {hex(fp.read_address(reg))}')

print("2. write 0xABCD in register 27")
fp.write_address(27, 0xABCD)

print("3. read register 27")
print(hex(fp.read_address(27)))

print("4. read register unixtime (32bit)")
print(hex(fp.read_register("unixtime")))

print("5. read DIO rain")
print(fp.read_dio("rain"))

print("6. read DIO norain")
print(fp.read_dio("norain"))

print("6. read DIO cover_closed")
print(fp.read_dio("cover_closed"))

print("7. read DIO cover_open")
print(fp.read_dio("cover_open"))

print("8. read DIO inverter")
print(fp.read_dio("inverter"))

print("9. turn on DIO inverter")
fp.write_dio("inverter", 1)

fp.close()
