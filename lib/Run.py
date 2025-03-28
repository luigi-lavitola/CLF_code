
import time
import datetime
import logging
from functools import partial
from logging.handlers import TimedRotatingFileHandler
from lib.DeviceCollection import DeviceCollection
from lib.Helpers import *

class RunBase:

    def __init__(self, dc : DeviceCollection):
        self.dc = dc

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
        if do_prepare:
            self.prepare()
        self.run()
        if do_finish:
            self.finish()


class RunMock(RunBase):

    def __init__(self, dc : DeviceCollection):
        super().__init__(dc) 

    def prepare(self):
        self.log(logging.INFO, "prepare")

    def run(self):
        self.log(logging.INFO, "run")
        time.sleep(10)

    def finish(self):
        self.log(logging.INFO, "finish")


class RunRaman(RunBase):

    def __init__(self, dc : DeviceCollection):
        super().__init__(dc)

        self.nshots = 75000
        #self.nshots = 1000

    def prepare(self):
        self.log(logging.INFO, "configure FPGA registers for RAMAN run")
        self.dc.fpga.write_register('pps_delay', 0)
        self.dc.fpga.write_bit('laser_en', 1)
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

        self.log(logging.INFO, "laser warmup and wait for laser fire auth")
        self.dc.laser.warmup()
        while not self.dc.laser.fire_auth():
            self.log(logging.INFO, c.temperature())
            time.sleep(1)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "radiometer 3700 setup")
        self.dc.get_radiometer('Rad1').setup()
        self.log(logging.INFO, "done")

    def run(self):
        self.log(logging.INFO, "start laser shots")
        self.dc.fpga.write_dio('laser_en', 1)
        self.dc.fpga.write_dio('laser_start', 1)

        self.log(logging.INFO, "wait for laser shots end")
        while True:
            ns = self.dc.fpga.read_register('shots_cnt')
            if ns == self.nshots:
                break
            self.log(logging.INFO, f'shots: {ns}, rain: {self.dc.fpga.read_dio("rain")}')
            time.sleep(1)
        self.log(logging.INFO, "done")

    def finish(self):
        self.log(logging.INFO, "unselect RAMAN beam")
        self.dc.fpga.write_dio('flipper_raman', False)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "set laser standby")
        self.dc.laser.standby()
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "close cover")
        WAIT_UNTIL_TRUE(self.dc.get_outlet("RAMAN_cover").off)
        self.log(logging.INFO, "done")

        self.log(logging.INFO, "wait cover closing")
        while self.dc.fpga.read_dio('cover_raman_open') == self.dc.fpga.read_dio('cover_raman_closed'):
            time.sleep(1)
        self.log(logging.INFO, "done")

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
        

class RunCLF(RunBase):

    def __init__(self, dc : DeviceCollection):
        super().__init__(dc)

    def prepare(self):
        self.log(logging.INFO, "prepare")

    def run(self):
        self.log(logging.INFO, "run")

    def finish(self):
        self.log(logging.INFO, "finish")

