#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.FPGARunControl import FPGARunControl

rc = FPGARunControl("/dev/runcontrol")
rc.connect()

print("1. dump FPGA registers (0-30)")
for reg in range(0,30):
   print(hex(rc.read_register(reg)))

print("2. write 0xABCD in register 27 (0x1B)")
rc.write_register(27, 0xABCD)

print("3. read register 27 (0x1B)")
print(hex(rc.read_register(27)))

print("4. read register 0 and register 1")
print(hex(rc.read_register(0)))
print(hex(rc.read_register(1)))

rc.close()
