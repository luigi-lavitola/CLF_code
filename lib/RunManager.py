
import threading
import time
from enum import Enum

class RunType(Enum):
    RAMAN = 1,
    FD = 2

class RunManager:

    def __init__(self, devices):
        self.runtype = None
        self.thr = None
        self.dc = devices

    def idle(self):
        return (self.thr is None or self.thr.is_alive() == False)

    def start(self, runtype): 
        if not isinstance(runtype, RunType):
            raise TypeError
        if self.idle() == True:
            self.runtype = runtype
            print(f"RUNMANAGER: start {self.runtype.name} run")
            self.thr = threading.Thread(target=self.exec)
            self.thr.start()

    def status(self):
        if self.idle():
            print(f"RUNMANAGER: idle")
        else:
            print(f"RUNMANAGER: run {self.runtype.name} in progress")

    def exec(self):
        print(f"Hi, I have to run {self.runtype.name}")
        time.sleep(5)

        # clean
        self.runtype = None
