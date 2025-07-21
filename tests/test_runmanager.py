import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import time

from lib.RunManager import RunManager, RunType

rm = RunManager(None, None)

rm.submit(RunType.RAMAN)
while rm.is_running():
    rm.print_status()
    time.sleep(1)

rm.submit(RunType.FD)
while rm.is_running():
    rm.print_status()
    time.sleep(1)


