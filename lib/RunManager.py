
import sys
import os
import time
import logging
import threading
import multiprocessing
import datetime
from functools import partial
from logging.handlers import TimedRotatingFileHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.DeviceCollection import DeviceCollection
from lib.HouseKeeping import HouseKeeping
from lib.RunCalendar import RunCalendar, RunEntry
from lib.Run import *

class RunManager:

    def __init__(self, dc : DeviceCollection, hk : HouseKeeping, params):
        self.dc = dc
        self.hk = hk
        self.params = params
        self.identity = self.params['identity']

        self.rc = RunCalendar('docs/ALLFDCalendar.txt', self.params)

        self.runs = []
        # fetch runs up to 1 day before 
        for day in self.rc.get_next_entries(dayoffset=1):
            for run in self.rc.get_timetable_for_entry(day):
                self.runs.append(run)

        # test - remove
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(seconds=10), runtype=RunType.MOCK, last=True))
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=1), runtype=RunType.RAMAN, last=False))
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=22), runtype=RunType.FD, last=True))
        #self.runs.append(RunEntry(datetime.datetime.now() + datetime.timedelta(minutes=3), runtype="mock", last=True))
        # test - remove

        # sort list of run and perform precise time alignment
        self.runlist = sorted(self.runs, key=lambda x: x.start_time)
        self.runlist = [run for run in self.runlist if run.start_time > datetime.datetime.now()]

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
        self.abort_in_progress = False

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
                    self.log(logging.WARN, f"run {nr.runtype.name} expected at {nr.start_time} not started due to scheduler disabled (check 'mode' in CLF cli)")
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
                self.log(logging.ERROR, f"{self.runentry.runtype.name} run cannot start due to alarms {self.hk.get_alarm()}")
            else:
                self.log(logging.INFO, f"start {self.runentry.runtype.name} run")
                if self.runentry.runtype == RunType.FD:
                    self.run = RunFD(self.dc)
                elif self.runentry.runtype == RunType.RAMAN:
                    #self.log(logging.INFO, "skipping Raman run for debug reasons") #self.run = RunRaman(self.dc)
                    self.run = RunRaman(self.dc, self.params)
                elif self.runentry.runtype == RunType.TANK:
                    self.run = RunTank(self.dc, self.params)
                elif self.runentry.runtype == RunType.CALIB:
                    self.run = RunCalib(self.dc, self.params)
                elif self.runentry.runtype == RunType.MOCK:
                    self.run = RunMock(self.dc, self.params)

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
            self.log(logging.ERROR, f"{self.runentry.runtype.name} run cannot start due to other job running")

    def stop(self):
        if self.job_is_running():
            self.job.terminate()
            self.job = multiprocessing.Process(target=self.run.abort)
            self.job.start()
            return 0
        return -1

    def kill(self):
        if self.job_is_running():
            self.job.terminate()
            self.log(logging.WARN, f"{self.runentry.runtype.name} run killed")
            return 0
        return -1

    def alarm_handler(self, msg):
        if self.job_is_running():
            self.log(logging.INFO, f"alarm received during run: {msg}")
            if not self.abort_in_progress:
                self.log(logging.INFO, f"start alarm handling")
                self.abort_in_progress = True
                self.job.terminate()
                self.log(logging.INFO, f"run aborted")
                self.log(logging.INFO, f"start devices shutdown")
                self.run.abort()
                self.log(logging.INFO, f"finish devices shutdown")
                self.abort_in_progress = False
            else:
                self.log(logging.INFO, f"alarm handling in progress")

    def print_status(self):
        if self.job_is_running():
            return f"run {self.runentry.runtype.name} in progress"
        else:
            return "idle"

    def close(self):
        self.loop = False
        self.thr.join()
        self.hk.unsubscribe(self.alarm_handler)
        self.log(logging.INFO, "end scheduler loop")
