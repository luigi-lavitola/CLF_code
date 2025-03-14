
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.RunManager import RunManager, RunType

### CONFIG 

cfg = Configuration()
cfg.read()

dc = DeviceCollection()
dc.init(cfg)

###

rm = RunManager(dc)
rm.status()

rm.start(RunType.RAMAN)
while not rm.idle():
    rm.status()
    time.sleep(1)


