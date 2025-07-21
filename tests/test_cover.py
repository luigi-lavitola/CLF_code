
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection


### HELPERS

def WAIT_UNTIL_TRUE(func):
    while True:
        if func():
            break

### CONFIG 

cfg = Configuration()
cfg.read()

dc = DeviceCollection()
dc.init(cfg)

### 


print("turn on inverter... ")
dc.fpga.write_dio('inverter', True)
print("done")

print("close Raman cover...")
WAIT_UNTIL_TRUE(dc.get_outlet("RAMAN_cover").off)
print("done")

while dc.fpga.read_dio('cover_raman_open') == dc.fpga.read_dio('cover_raman_closed'):
    time.sleep(1)

print("turn off Radiometer outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('radiometer').off)
print("done")

print("turn off Laser outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('laser').off)
print("done")

print("turn off VXM outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('VXM').off)
print("done")

print("turn off inverter... ")
dc.fpga.write_dio('inverter', False)
print("done")
