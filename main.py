#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import threading

from cmd2 import Cmd
from apscheduler.schedulers.background import BackgroundScheduler

from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.HouseKeeping import HouseKeeping

class App(Cmd):

    def __init__(self, dc):
        super().__init__(persistent_history_file='~/.main_history', persistent_history_length=100)
        self.prompt = "CLF> "
        self.dc = dc

### CONFIG

cfg = Configuration()
cfg.read()

dc = DeviceCollection()
dc.init(cfg)

hk = HouseKeeping()
thr_hk = threading.Thread(target=hk.run)
thr_hk.start()

###

app = App(dc)
app.cmdloop()
