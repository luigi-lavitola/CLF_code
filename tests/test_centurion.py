#!/usr/bin/env python3

import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.Centurion import Centurion

c = Centurion("/dev/ttyr01")
time.sleep(1)
c.send_command("$STATUS")
#c.set_mode()
#time.sleep(5)
#c.warmup()
#c.read_bytes()
