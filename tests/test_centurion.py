#!/usr/bin/env python3

import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.Centurion import Centurion

c = Centurion("/dev/ttyr01")
c.set_mode()
c.warmup()
print("wait for laser fire auth...")
while not c.fire_auth():
    print(c.temperature())
    time.sleep(1)
c.standby()
c.sleep()
