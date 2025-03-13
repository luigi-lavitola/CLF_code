
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection

cfg = Configuration()
cfg.read()

dc = DeviceCollection()
dc.init(cfg)


