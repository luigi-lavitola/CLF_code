
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
        self.loop = True
        self.abort_in_progress = False

        self.hk.subscribe(self.alarm_handler)

        # start the thread only when every attribute it uses exists
        self.thr = threading.Thread(target=self.scheduler)
        self.thr.start()

    def scheduler(self):
        self.log(logging.INFO, "start scheduler loop")
        nr = self.next_run()
        if nr is None:
            self.log(logging.WARN, "no scheduled runs left in the calendar")
        while self.loop:
            try:
                if nr is not None and datetime.datetime.now() > nr.start_time:
                    if self.scheduler_running:
                        # start scheduled run
                        self.submit(nr, source='runmanager')
                    else:
                        # warn user about scheduler disabled
                        self.log(logging.WARN, f"run {nr.runtype.name} expected at {nr.start_time} not started due to scheduler disabled (check 'mode' in CLF cli)")
                    self.runlist.remove(nr)
                    nr = self.next_run()
                    if nr is None:
                        self.log(logging.WARN, "no scheduled runs left in the calendar")
            except Exception as e:
                # never let the scheduler thread die: drop the entry that failed and go on
                self.log(logging.ERROR, f"scheduler error on {nr}: {e!r}", exc_info=True)
                if nr in self.runlist:
                    self.runlist.remove(nr)
                nr = self.next_run()
            try:
                self.idle_check(nr)
            except Exception as e:
                self.log(logging.ERROR, f"idle shutdown check failed: {e!r}", exc_info=True)
            time.sleep(1)

    # no run within this time and instruments still powered (inverter on): shut down.
    # Longer than the gaps of a night (FD every 15 min, Raman end+30, calib end+60).
    IDLE_SHUTDOWN_S = 45 * 60
    IDLE_CHECK_PERIOD_S = 60

    def idle_check(self, nr):
        """Auto mode only: shut the station down when nothing is running, the inverter is
        on and the next run is more than IDLE_SHUTDOWN_S away (or there is none), e.g.
        when the last run of the night did not start (alarm, manual mode, busy)."""
        now = time.monotonic()
        if not self.scheduler_running or self.job_is_running() or now < getattr(self, '_next_idle_check', 0):
            return
        self._next_idle_check = now + self.IDLE_CHECK_PERIOD_S
        if nr is not None and (nr.start_time - datetime.datetime.now()).total_seconds() <= self.IDLE_SHUTDOWN_S:
            return
        if self.dc.fpga.read_dio('inverter'):
            self.start_shutdown(f"no run in the next {self.IDLE_SHUTDOWN_S // 60} min"
                                + ("" if nr is None else f" (next: {nr.runtype.name} at {nr.start_time})"))

    def start_shutdown(self, reason):
        """Start a RunShutdown job (not refused on alarms: it is what alarms need)."""
        if self.job_is_running():
            return False
        self.log(logging.WARN, f"station shutdown: {reason}")
        self.runentry = RunEntry(datetime.datetime.now(), RunType.SHUTDOWN, False, True)
        self.run = RunShutdown(self.dc, self.params)
        self.job = multiprocessing.Process(target=self.run.execute)
        self.job.start()
        return True

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

    RUN_CLASSES = {
        RunType.FD: RunFD,
        RunType.RAMAN: RunRaman,
        RunType.TANK: RunTank,
        RunType.CALIB: RunCalib,
        RunType.MOCK: RunMock,
    }

    def submit(self, runentry, source):
        """Start a run. Returns True if the job was started."""
        if not isinstance(runentry, RunEntry):
            raise TypeError
        name = runentry.runtype.name

        # self.runentry / self.run describe the job in progress: update them only when a new job starts
        if self.job_is_running():
            self.log(logging.ERROR, f"{name} run cannot start due to other job running ({self.runentry.runtype.name})")
            return False

        alarms = self.hk.get_alarm()
        if len(alarms) > 0:
            self.log(logging.ERROR, f"{name} run cannot start due to alarms {alarms}")
            return False

        run_class = self.RUN_CLASSES.get(runentry.runtype)
        if run_class is None:
            self.log(logging.ERROR, f"{name} run cannot start: unknown run type")
            return False

        self.log(logging.INFO, f"start {name} run")
        self.runentry = runentry
        self.run = run_class(self.dc, self.params)

        if source == 'runmanager' and runentry.last == False:
            # scheduled run that is not the last of the night: keep instruments on (no finish)
            self.job = multiprocessing.Process(target=self.run.execute, args=(True, False,))
        else:
            self.job = multiprocessing.Process(target=self.run.execute)
        self.job.start()
        return True

    def _terminate_job(self):
        """Terminate the run process without leaving the FPGA in the middle of a transaction.

        The FPGA serial lock is shared with the child: the parent takes it first, so the
        child completes its current register access and then waits; only then it is
        terminated. If the lock is not released (child stuck while holding it), the child
        is terminated anyway and the lock replaced, otherwise every later FPGA access of
        this process (housekeeping, scheduler, CLI) would wait for a dead owner."""
        fpga = getattr(self.dc, 'fpga', None)
        mutex = getattr(fpga, 'mutex', None)
        acquired = mutex.acquire(timeout=fpga.LOCK_TIMEOUT_S) if mutex is not None else False
        try:
            self.job.terminate()
            self.job.join(5)
        finally:
            if acquired:
                mutex.release()
        if mutex is not None and not acquired:
            fpga.mutex = multiprocessing.Lock()
            self.log(logging.ERROR, "FPGA lock held by the terminated run process: replaced")

    def stop(self):
        if self.job_is_running():
            self._terminate_job()
            self.job = multiprocessing.Process(target=self.run.abort)
            self.job.start()
            return 0
        return -1

    def kill(self):
        if self.job_is_running():
            self._terminate_job()
            self.log(logging.WARN, f"{self.runentry.runtype.name} run killed")
            return 0
        return -1

    def alarm_handler(self, msg):
        if self.job_is_running():
            self.log(logging.INFO, f"alarm received during run: {msg}")
            if not self.abort_in_progress:
                self.log(logging.INFO, f"start alarm handling")
                self.abort_in_progress = True
                try:
                    self._terminate_job()
                    self.log(logging.INFO, f"run aborted")
                    self.log(logging.INFO, f"start devices shutdown")
                    self.run.abort()
                    self.log(logging.INFO, f"finish devices shutdown")
                finally:
                    # an exception in abort() must not block the handling of every later alarm
                    self.abort_in_progress = False
            else:
                self.log(logging.INFO, f"alarm handling in progress")
        elif self.dc is not None and self.dc.fpga.read_dio('inverter'):
            # alarm between runs (auto and manual mode): instruments may still be on
            # (scheduled runs keep them on until the last run of the night)
            self.start_shutdown(f"alarm {[a.get('name') for a in msg]}")

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
