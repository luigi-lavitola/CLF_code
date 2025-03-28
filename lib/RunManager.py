
import sys
import os
import time
import logging
import threading
import multiprocessing
import datetime
from enum import Enum
from functools import partial
from logging.handlers import TimedRotatingFileHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.DeviceCollection import DeviceCollection
from lib.HouseKeeping import HouseKeeping
from lib.RunCalendar import RunCalendar, RunEntry
from lib.Run import *

class RunType(Enum):
    RAMAN = 1,
    FD = 2,
    CELESTE = 3,
    CALIB = 4,
    MOCK = 5,

class RunManager:

    def __init__(self, dc : DeviceCollection, hk : HouseKeeping):
        self.dc = dc
        self.hk = hk

        self.rc = RunCalendar('docs/ALLFDCalendar.txt')

        self.runs = []
        for day in self.rc.get_next_entries():
            for run in self.rc.get_timetable_for_entry(day):
                self.runs.append(run)

        # test - remove
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(seconds=10), runtype="mock", last=True))
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=1), runtype="mock"))
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=2), runtype="mock"))
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=3), runtype="mock", last=True))
        # test - remove

        self.runlist = sorted(self.runs, key=lambda x: x.start_time)

        self.logger = logging.getLogger("run")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/run.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})

        self.runentry = None
        self.run = None
        self.job = None
        self.scheduler_running = True
        self.thr = threading.Thread(target=self.scheduler)
        self.thr.start()
        self.loop = True

        self.hk.subscribe(self.alarm_handler)

    def scheduler(self):
        self.log(logging.INFO, "start scheduler loop")
        nr = self.next_run()
        while self.loop:
            if datetime.datetime.now() > nr.start_time:
                if self.scheduler_running:
                    # start scheduled run 
                    self.submit(nr, source='runmanager')
                else:
                    # warn user about scheduler disabled
                    self.log(logging.WARN, f"run {nr.runtype} expected at {nr.start_time} not started due to scheduler disabled (check 'mode' in CLF cli)")
                self.runlist.remove(nr)
                nr = self.next_run()
            time.sleep(1)

    def start_scheduler(self):
        self.scheduler_running = True

    def stop_scheduler(self):
        self.scheduler_running = False
    
    def job_is_running(self):
        if self.job is None:
            return False
        return self.job.is_alive()

    def next_run(self):
        for run in self.runlist:
            if run.start_time > datetime.datetime.now():
                return run
        return None

    def submit(self, runentry, source): 
        if not isinstance(runentry, RunEntry):
            raise TypeError
        self.runentry = runentry
        if self.job_is_running() == False:
            if len(self.hk.get_alarm()) > 0:
                self.log(logging.ERROR, f"{self.runentry.runtype} run cannot start due to alarms {self.hk.get_alarm()}")
            else:
                self.log(logging.INFO, f"start {self.runentry.runtype} run")
                if self.runentry.runtype == 'clf':
                    self.run = RunCLF(self.dc)
                elif self.runentry.runtype == 'raman':
                    self.run = RunRaman(self.dc)
                elif self.runentry.runtype == 'mock':
                    self.run = RunMock(self.dc)
                if source == 'cli':     # run started from command line interface
                    self.job = multiprocessing.Process(target=self.run.execute)
                    self.job.start()
                else:                   # run started from scheduler
                    if runentry.last == False:
                        self.job = multiprocessing.Process(target=self.run.execute, args=(True, False,))
                    else:
                        self.job = multiprocessing.Process(target=self.run.execute)
                    self.job.start()
        else:
            self.log(logging.ERROR, f"{self.runentry.runtype} run cannot start due to other job running")

    def alarm_handler(self, msg):
        if self.job_is_running():
            self.log(logging.INFO, f"alarm received during run: {msg}")
            self.job.terminate()
            self.log(logging.INFO, f"run aborted")
            self.log(logging.INFO, f"start devices shutdown")
            self.run.finish()
            self.log(logging.INFO, f"finish devices shutdown")

    def print_status(self):
        if self.job_is_running():
            print(f"RUNMANAGER: run {self.runentry.runtype} in progress")
        else:
            print(f"RUNMANAGER: idle")

    def close(self):
        self.loop = False
        self.thr.join()
        self.hk.unsubscribe(self.alarm_handler)
        self.log(logging.INFO, "end scheduler loop")
