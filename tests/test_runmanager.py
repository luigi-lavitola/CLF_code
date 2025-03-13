import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import time

from lib.RunManager import RunManager, RunType

rm = RunManager(None)
rm.start(RunType.RAMAN)
while not rm.idle():
    rm.status()
    time.sleep(1)

rm.start(RunType.FD)
while not rm.idle():
    rm.status()
    time.sleep(1)


