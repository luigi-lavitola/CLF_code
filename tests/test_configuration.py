import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection

cfg = Configuration()
cfg.read()

dc = DeviceCollection()
dc.init(cfg)

ol = dc.get_outlet("laser")
ol.on()
print(ol.status())

dc.laser.comm_test()

ol.off()
print(ol.status())

#rm_outlet = dc.get_outlet("radiometer")
#print(rm_outlet.status())
#rm_outlet.on()

#rm = dc.get_radiometer("Rad1")
#rm.info()
#print(f'TG = {rm.get("TG")}')
#rm.set("TG", 3)
#print(f'TG = {rm.get("TG")}')

vxm_outlet = dc.get_outlet("VXM")
print(vxm_outlet.status())
vxm_outlet.on()

mt = dc.get_motor("LwNorthSouth")
print(mt.is_connected())

