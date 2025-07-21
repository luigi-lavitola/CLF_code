#!/usr/bin/env python3

import sys
import os
import threading
import multiprocessing
import time
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

print("4.1 write pulse period 3_000_000_000 (32bit)")
fp.write_register('pulse_period', 3_000_000_000)

print("4.2 read pulse period (32bit)")
print(hex(fp.read_register("pulse_period")))

print("5. read DIO rain")
print(fp.read_dio("rain"))

print("6. read DIO norain")
print(fp.read_dio("norain"))

print("6. read DIO cover_raman_closed")
print(fp.read_dio("cover_raman_closed"))

print("7. read DIO cover_raman_open")
print(fp.read_dio("cover_raman_open"))

print("8. read DIO inverter")
print(fp.read_dio("inverter"))

print("9. turn on DIO inverter")
fp.write_dio("inverter", 1)

print("10. read pps_ok flag")
print(fp.read_bit("pps_ok"))

print("11. turn off DIO inverter")
fp.write_dio("inverter", 0)

"""
print("test mutual exclusion")

def func():
    for _ in range(100):
        print(f'{hex(fp.read_register("unixtime"))}')
        time.sleep(0.01)

p1 = multiprocessing.Process(target=func)
p2 = multiprocessing.Process(target=func)
thr1 = threading.Thread(target=func)
thr2 = threading.Thread(target=func)

print("- start process #1")
p1.start()
print("- start process #2")
p2.start()

print("- start thread #1")
thr1.start()
print("- start thread #2")
thr2.start()

p1.join()
print("- end process #1")
p2.join()
print("- end process #2")

thr1.join()
print("- end thread #1")
thr2.join()
print("- end thread #2")
"""

fp.close()
