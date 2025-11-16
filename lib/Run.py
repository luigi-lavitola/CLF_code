
import time
import datetime
import logging
import paramiko
from functools import partial
from enum import Enum
from logging.handlers import TimedRotatingFileHandler
from lib.DeviceCollection import DeviceCollection
from lib.Helpers import *

class RunType(Enum):
    RAMAN = 1,
    FD = 2,
    TANK = 3,
    CALIB = 4,
    MOCK = 5,

class RunBase:

    def __init__(self, dc : DeviceCollection, params):
        self.dc = dc
        self.params = params
        self.identity = self.params['identity']

        self.logger = logging.getLogger("run")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/run.log', when='midnight', 
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})

    def execute(self, do_prepare=True, do_finish=True):
        ret = None
        if do_prepare:
            try:
                ret = self.prepare()
            except Exception as e:
                self.log(logging.ERROR, f"exception occurred during prepare: {e}")
        if ret == 0:        # check if run preparation is completed
            try:
                self.run()
            except Exception as e:
                self.log(logging.ERROR, f"exception occurred during run: {e}") 
        if do_finish:
            try:
                self.finish()
            except Exception as e:
                self.log(logging.ERROR, f"exception occurred during finish: {e}")


class RunMock(RunBase):

    def __init__(self, dc : DeviceCollection, params):
        super().__init__(dc, params) 

    def prepare(self):
        self.log(logging.INFO, "prepare")
        return 0

    def run(self):
        self.log(logging.INFO, "run")
        time.sleep(10)

    def finish(self):
        self.log(logging.INFO, "finish")

    def abort(self):
        self.log(logging.INFO, "abort")
        self.finish()

class RunRaman(RunBase):

    def __init__(self, dc : DeviceCollection, params):
        super().__init__(dc, params)

        self.nshots = 75000

    def prepare(self):
        self.log(logging.INFO, "configure FPGA registers for RAMAN run")
        self.dc.fpga.write_register('pps_delay', 0)
        self.dc.fpga.write_bit('laser_en', 1)
        self.dc.fpga.write_bit('timestamp_en', 0)
        self.dc.fpga.write_register('pulse_width', 10_000)  # 100 us
        self.dc.fpga.write_register('pulse_energy', 17_400) # 140 us = 174 us, maximum
        self.dc.fpga.write_register('pulse_period', 1_000_000) # 10 ms
        self.dc.fpga.write_register('shots_num', self.nshots)

        self.dc.fpga.write_register('mux_bnc_0', 0b0010)
        self.dc.fpga.write_register('mux_bnc_1', 0b0010)
        self.dc.fpga.write_register('mux_bnc_2', 0b0010)
        self.dc.fpga.write_register('mux_bnc_3', 0b0010)
        self.dc.fpga.write_register('mux_bnc_4', 0b0010)
        self.log(logging.INFO, "done")
        
        self.log(logging.INFO, "turn on inverter")
        if self.dc.fpga.read_dio('inverter') == True:
            self.log(logging.INFO, "already on - skip")
        else:
            self.dc.fpga.write_dio('inverter', True)
            self.log(logging.INFO, "done")

            self.log(logging.INFO, "wait RPC and MOXA power up")
            for _ in range(10):
                time.sleep(1)
            self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on Radiometer outlet")
        if self.dc.get_outlet('radiometer').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('radiometer').on)
            self.log(logging.INFO, "done") 

        self.log(logging.INFO, "turn on Laser outlet")
        if self.dc.get_outlet('laser').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('laser').on)
            self.log(logging.INFO, "done") 

        self.log(logging.INFO, "turn on VXM outlet")
        if self.dc.get_outlet('VXM').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('VXM').on)
            self.log(logging.INFO, "done") 

        self.log(logging.INFO, "wait power up")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")
        
        self.log(logging.INFO, "laser setup")
        self.dc.laser.set_mode(qson = 1, dpw = 140)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "radiometer 3700 setup")
        self.dc.get_radiometer('Rad1').setup()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "select RAMAN beam")
        self.dc.fpga.write_dio('flipper_raman', True)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on RAMAN DAQ...")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("RAMAN_inst").on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "open RAMAN cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("RAMAN_cover").on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover opening...")
        cover_timeout_s = 120
        t = 0
        while self.dc.fpga.read_dio('cover_raman_open') == self.dc.fpga.read_dio('cover_raman_closed'):
            if t >= cover_timeout_s:
                self.log(logging.ERROR, f"cover open timeout ({cover_timeout_s}) - run interrupted")
                return -1
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "laser warmup and wait for laser fire auth")
        self.dc.laser.warmup()
        laser_timeout_s = 120
        t = 0
        while not self.dc.laser.fire_auth():
            if t >= laser_timeout_s:
                self.log(logging.ERROR, f"laser fire authorization timeout ({laser_timeout_s}s) - run interrupted")
                return -1
            self.log(logging.INFO, self.dc.laser.temperature())
            #self.dc.laser.standby()
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "set laser in fire mode...")
        self.dc.laser.fire()
        self.log(logging.INFO, "done")

        return 0

    def run(self):
        self.log(logging.INFO, "start laser shots")
        self.dc.fpga.write_dio('laser_en', 1)
        self.dc.fpga.write_dio('laser_start', 1)

        self.log(logging.INFO, "start DAQ process on RAMAN PC")
        hostname = "192.168.218.191"
        username = "root"
        password = "ariag25"

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username=username, password=password, look_for_keys=False, allow_agent=False)

        stdin, stdout, stderr = client.exec_command("./start12 >& /media/data/rdata/start12.log & echo $!")
        pid = stdout.read().decode().strip()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for laser shots end")
        while True:
            ns = self.dc.fpga.read_register('shots_cnt')
            if ns == self.nshots:
                break
            self.log(logging.INFO, f'shots: {ns}')
            time.sleep(20)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "waiting for RAMAN DAQ process to finish...")
        while True:
            stdin, stdout, stderr = client.exec_command(f"ps -p {pid} -o comm=")
            process_name = stdout.read().decode().strip()

            if not process_name:
                break
            else:
                time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "unselect RAMAN beam")
        self.dc.fpga.write_dio('flipper_raman', False)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("RAMAN_cover").off)
        self.log(logging.INFO, "done")

        cover_timeout_s = 120
        t = 0
        self.log(logging.INFO, "wait for open limit switch release")
        while self.dc.fpga.read_dio('cover_raman_open') == True:
            if t >= cover_timeout_s:
                self.log(logging.ERROR, f"limit switch release timeout ({cover_timeout_s}) - run interrupted")
                return -1
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        cover_timeout_s = 120
        t = 0
        self.log(logging.INFO, "wait cover closing")
        while self.dc.fpga.read_dio('cover_raman_open') == self.dc.fpga.read_dio('cover_raman_closed'):
            if t >= laser_timeout_s:
                self.log(logging.ERROR, f"cover close timeout ({cover_timeout_s}) - run interrupted")
                return -1
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")
        
        time.sleep(2)
        self.log(logging.INFO, "turn off RAMAN DAQ...")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("RAMAN_inst").off)
        self.log(logging.INFO, "done")

    def finish(self):

        self.log(logging.INFO, "turn off Radiometer outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('radiometer').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off Laser outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('laser').off) 
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off VXM outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('VXM').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off inverter")
        self.dc.fpga.write_dio('inverter', False)
        self.log(logging.INFO, "done")

    def abort(self):

        self.log(logging.INFO, "abort")
        
        self.dc.fpga.write_bit('laser_en', 0)

        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("RAMAN_cover").off)
        self.log(logging.INFO, "done")

        cover_timeout_s = 120
        t = 0
        self.log(logging.INFO, "wait for open limit switch release")
        while self.dc.fpga.read_dio('cover_raman_open') == True:
            if t >= cover_timeout_s:
                self.log(logging.ERROR, f"limit switch release timeout ({cover_timeout_s}) - run interrupted")
                return -1
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        cover_timeout_s = 120
        t = 0
        self.log(logging.INFO, "wait cover closing")
        while self.dc.fpga.read_dio('cover_raman_open') == self.dc.fpga.read_dio('cover_raman_closed'):
            if t >= laser_timeout_s:
                self.log(logging.ERROR, f"cover close timeout ({cover_timeout_s}) - run interrupted")
                return -1
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "unselect RAMAN beam")
        self.dc.fpga.write_dio('flipper_raman', False)
        self.log(logging.INFO, "done")
        
        self.finish()
        

class RunFD(RunBase):

    def __init__(self, dc : DeviceCollection, params):
        super().__init__(dc, params)
        self.nshots = 50
        
    def prepare(self):
        self.log(logging.INFO, "prepare")
        self.log(logging.INFO, "configure FPGA registers for FD run")
        value = self.params[self.identity]['fd_pps_delay']
        self.dc.fpga.write_register('pps_delay', value) 
        self.dc.fpga.write_bit('laser_en', 1)
        self.dc.fpga.write_bit('timestamp_en', 1)

        self.dc.fpga.write_register('pulse_width', 10_000)  # 100 us
        self.dc.fpga.write_register('pulse_energy', 17_400) # 140 us = 174 us, maximum
        self.dc.fpga.write_register('pulse_period', 100_000_000)  # 1000 ms 1 hz
        self.dc.fpga.write_register('shots_num', self.nshots)

        self.dc.fpga.write_register('mux_bnc_0', 0b0010)
        self.dc.fpga.write_register('mux_bnc_1', 0b0010)
        self.dc.fpga.write_register('mux_bnc_2', 0b0010)
        self.dc.fpga.write_register('mux_bnc_3', 0b0010)
        self.dc.fpga.write_register('mux_bnc_4', 0b0010)
        self.log(logging.INFO, "done")
        
        self.log(logging.INFO, "turn on inverter")
        if self.dc.fpga.read_dio('inverter') == True:
            self.log(logging.INFO, "already on - skip")
        else:
            self.dc.fpga.write_dio('inverter', True)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait RPC and MOXA power up")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on Radiometer outlet")
        if self.dc.get_outlet('radiometer').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('radiometer').on)
        self.log(logging.INFO, "done") 

        self.log(logging.INFO, "turn on Laser outlet")
        if self.dc.get_outlet('laser').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('laser').on)
        self.log(logging.INFO, "done") 

        self.log(logging.INFO, "turn on VXM outlet")
        if self.dc.get_outlet('VXM').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('VXM').on)
        self.log(logging.INFO, "done") 

        self.log(logging.INFO, "wait power up")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "radiometer 3700 setup")
        self.dc.get_radiometer('Rad1').setup()
        self.log(logging.INFO, "done")
        
        self.log(logging.INFO, "laser setup")
        self.dc.laser.set_mode(qson = 1, dpw = 140)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "laser warmup and wait for laser fire auth")
        self.dc.laser.warmup()
        laser_timeout_s = 120
        t = 0
        while not self.dc.laser.fire_auth():
            if t >= laser_timeout_s:
                self.log(logging.ERROR, f"laser fire authorization timeout ({laser_timeout_s}s) - run interrupted")
                return -1
            self.log(logging.INFO, self.dc.laser.temperature())
            #self.dc.laser.standby()
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "select vertical beam")
        self.dc.fpga.write_dio('flipper_raman', False)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "open vertical cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("Vert_cover").on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover opening...")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "set laser in fire mode...")
        self.dc.laser.fire()
        self.log(logging.INFO, "done")

        return 0

    def run(self):
        self.log(logging.INFO, "start FD Run")
        self.dc.fpga.write_dio('laser_en', 1)
        self.dc.fpga.write_dio('laser_start', 1)

        for i in range(self.nshots):
            power=self.dc.get_radiometer('Rad1').read_power()
            seconds, counter, pps, counter_cycles = self.dc.data.read_event()
            self.log(logging.INFO, f'power {i} shot: {power}, seconds: {seconds}, counter: {counter}, pps distance: {pps}ns, counter cycle: {counter_cycles}')
        
        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        #self.dc.get_outlet("Vert_cover").off()
        WAIT_UNTIL_TRUE(self.dc.get_outlet("Vert_cover").off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover closing...")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

    def finish(self):
        self.log(logging.INFO, "finish")
        self.log(logging.INFO, "turn off Radiometer outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('radiometer').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off Laser outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('laser').off) 
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off VXM outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('VXM').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off inverter")
        self.dc.fpga.write_dio('inverter', False)
        self.log(logging.INFO, "done")
        
    def abort(self):
        self.log(logging.INFO, "abort")

        self.dc.fpga.write_dio('laser_en', 0)

        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        #self.dc.get_outlet("Vert_cover").off()
        WAIT_UNTIL_TRUE(self.dc.get_outlet("Vert_cover").off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover closing...")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.finish()

class RunTank(RunBase):

    def __init__(self, dc : DeviceCollection, params):
        super().__init__(dc, params) 
        self.nshots = 3
        self.tankname = self.params[self.identity]['tank_name']

    def prepare(self):
        self.log(logging.INFO, "prepare")
        print("configure FPGA registers for TANK run ({self.tankname})...")
        value = self.params[self.identity]['tank_pps_delay']
        self.dc.fpga.write_register('pps_delay', value) 
        self.dc.fpga.write_bit('laser_en', 1)
        self.dc.fpga.write_register('pulse_width', 10_000)  # 100 us
        self.dc.fpga.write_register('pulse_energy', 17_400) # 140 us = 174 us, maximum
        #self.dc.fpga.write_register('pulse_period', 3_000_000_000) # 30_000 ms 
        self.dc.fpga.write_register('pulse_period', 100_000_000)  # 1000 ms 1 hz
        self.dc.fpga.write_register('shots_num', self.nshots)

        self.dc.fpga.write_register('mux_bnc_0', 0b0010)
        self.dc.fpga.write_register('mux_bnc_1', 0b0010)
        self.dc.fpga.write_register('mux_bnc_2', 0b0010)
        self.dc.fpga.write_register('mux_bnc_3', 0b0010)
        self.dc.fpga.write_register('mux_bnc_4', 0b0010)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on inverter")
        if self.dc.fpga.read_dio('inverter') == True: 
            self.log(logging.INFO, "already on - skip")
        else:
            self.dc.fpga.write_dio('inverter', True)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait RPC and MOXA power up")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on Radiometer outlet")
        if self.dc.get_outlet('radiometer').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('radiometer').on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on Laser outlet")
        if self.dc.get_outlet('laser').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('laser').on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn on VXM outlet")
        if self.dc.get_outlet('VXM').status() == True:
            self.log(logging.INFO, "already on - skip")
        else:
            WAIT_UNTIL_TRUE(self.dc.get_outlet('VXM').on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait power up")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "radiometer 3700 setup")
        self.dc.get_radiometer('Rad1').setup()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "laser setup")
        self.dc.laser.set_mode(qson = 1, dpw = 140)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "laser warmup and wait for laser fire auth")
        self.dc.laser.warmup()
        laser_timeout_s = 120
        t = 0
        while not self.dc.laser.fire_auth():
            if t >= laser_timeout_s:
                self.log(logging.ERROR, f"laser fire authorization timeout ({laser_timeout_s}s) - run interrupted")
                return -1
            self.log(logging.INFO, self.dc.laser.temperature())
            #self.dc.laser.standby()
            time.sleep(1)
            t += 1
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "select vertical beam")
        self.dc.fpga.write_dio('flipper_raman', False)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "open vertical cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("Vert_cover").on)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover opening...")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "set laser in fire mode...")
        self.dc.laser.fire()
        self.log(logging.INFO, "done")

        return 0

    def run(self):
        self.log(logging.INFO, f"start TANK Run ({self.tankname})")
        self.dc.fpga.write_dio('laser_en', 1)
        self.dc.fpga.write_dio('laser_start', 1)

        for i in range(self.nshots):
            power=self.dc.get_radiometer('Rad1').read_power()
            seconds, counter, pps, counter_cycles = self.dc.data.read_event()
            self.log(logging.INFO, f'power {i} shot: {power}, seconds: {seconds}, counter: {counter}, pps distance: {pps}ns, counter cycle: {counter_cycles}')

        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("Vert_cover").off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover closing...")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

    def finish(self):
        self.log(logging.INFO, "finish")
        self.log(logging.INFO, "turn off Radiometer outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('radiometer').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off Laser outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('laser').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off VXM outlet")
        WAIT_UNTIL_TRUE(self.dc.get_outlet('VXM').off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "turn off inverter")
        self.dc.fpga.write_dio('inverter', False)
        self.log(logging.INFO, "done")

    def abort(self):
        self.log(logging.INFO, "abort")

        self.dc.fpga.write_dio('laser_en', 0)

        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("Vert_cover").off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait for cover closing...")
        for _ in range(10):
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.finish()


class RunCalib(RunBase):

    def __init__(self, dc : DeviceCollection, params):
        super().__init__(dc, params) 

    def prepare(self):
        self.log(logging.INFO, "prepare")
        return 0

    def run(self):
        self.log(logging.INFO, "run")
        time.sleep(10)
 
    def finish(self):
        self.log(logging.INFO, "finish")

    def abort(self):
        self.log(logging.INFO, "abort")
        self.finish()

