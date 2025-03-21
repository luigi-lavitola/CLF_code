import os
import sys
import time
import paramiko
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.FPGAData import FPGAData

data = FPGAData("/dev/runcontrol")


for i in range(10):
    data.read_event()