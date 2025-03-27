
import os
import sys
import time
import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from pyftdi.spi import SpiController
from functools import partial
from lib.TLA2518 import TLA2518
from lib.LTC2983 import LTC2983
from lib.LTC2983_const import *
from lib.FPGADevice import FPGADevice

class HouseKeeping:

    __subscribers = []

    def __init__(self):
        self.spi1 = SpiController()
        self.spi1.configure('ftdi://ftdi:4232h/1')
        self.slave1 = self.spi1.get_port(cs=0, freq=2E6, mode=0)
        self.ltc = LTC2983()
        self.tcont = self.ltc.get_ftdi_backend(self.slave1)

        self.spi2 = SpiController()
        self.spi2.configure('ftdi://ftdi:4232h/2')
        self.slave2 = self.spi2.get_port(cs=0, freq=30E6, mode=0)
        self.tla = TLA2518()
        self.adc = self.tla.get_ftdi_backend(self.slave2)

        self.log = logging.getLogger("housekeeping")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler = TimedRotatingFileHandler('logs/hk.log', when='midnight', atTime=datetime.time(hour=18, minute=0))
        handler.setFormatter(formatter)
        self.log.addHandler(handler)
        self.log.setLevel(logging.INFO)

        try:
            self.fpga = FPGADevice("/dev/runcontrol")
        except:
            self.fpga = FPGADevice.getInstance()

        for ch in [4, 6, 8, 10, 12, 14, 16, 18, 20]:
            self.tcont.config_channel(ch, SENSOR_TYPE__THERMISTOR_44006_10K_25C |
                THERMISTOR_RSENSE_CHANNEL__2 |
                THERMISTOR_DIFFERENTIAL |
                THERMISTOR_EXCITATION_MODE__SHARING_ROTATION |
                THERMISTOR_EXCITATION_CURRENT__AUTORANGE)

        self.data = [
            { "dev": "tla", "name": "battery1", "channel": 0, "value": 0, 
                "unit": "V", "coeff": 0.012698329443235162, "min": 11.5, "max": 15, "alarm": False},
            { "dev": "tla", "name": "battery2", "channel": 1, "value": 0, 
                "unit": "V", "coeff": 0.012857486052905534, "min": 11.5, "max": 15, "alarm": False},
            { "dev": "tla", "name": "solar2", "channel": 2, "value": 0, 
                "unit": "V", "coeff": 0.012580072988236255 },
            { "dev": "tla", "name": "relay", "channel": 5, "value": 0, 
                "unit": "V", "coeff": 0.012 },
            { "dev": "tla", "name": "solar1", "channel": 7, "value": 0, 
                "unit": "V", "coeff": 0.012597657636342127 },
            { "dev": "ltc", "name": "t0", "channel": 4, "value": 0, "unit": "degC", },
            { "dev": "ltc", "name": "t1", "channel": 6, "value": 0, "unit": "degC", },
            { "dev": "ltc", "name": "t2", "channel": 8, "value": 0, "unit": "degC", },
            { "dev": "ltc", "name": "t3", "channel": 10, "value": 0, "unit": "degC", },
            { "dev": "ltc", "name": "t4", "channel": 12, "value": 0, "unit": "degC", },
            { "dev": "dio", "name": "rain", "value": False, "error": False, "alarm": False},
            { "dev": "dio", "name": "cover_steer_open", "value": False },
            { "dev": "dio", "name": "cover_raman_open", "value": False },
            # add cover steer and raman
        ]

    def collect_data(self):
        for d in self.data:
            if d['dev'] == 'tla':
                d['value'] = round(self.adc.read_channel(d['channel']) * d['coeff'], 2)
            elif d['dev'] == 'ltc':
                d['value'] = round(self.tcont.read_temperature(d['channel']), 2)
            elif d['dev'] == 'dio':
                if d['name'] == 'rain':
                    d['error'] = self.fpga.read_dio('rain') == self.fpga.read_dio('norain')
                    d['value'] = self.fpga.read_dio('rain')
                else:
                    d['value'] = self.fpga.read_dio(d['name'])

    def log_data(self):
        # new file at 6 PM
        s = ''
        for d in self.data:
           s += f" {d['name']}={d['value']}[{d.get('unit', '')}]" 
        self.log.info(s)

    def check_alarm(self):
        alarm_data = []
        for d in self.data:
            if d.get('alarm', None) is not None:
                if d['dev'] == 'tla':
                    if (d['value'] < d['min']) or (d['value'] > d['max']):
                        d['alarm'] = True
                        alarm_data.append(d)
                    else:
                        d['alarm'] = False
                elif d['dev'] == 'dio':
                    if d['name'] == 'rain':
                        if d['value'] or d['error']:
                            d['alarm'] = True
                            alarm_data.append(d)
                        else:
                            d['alarm'] = False

        if len(alarm_data):
            self.notify_subscribers(alarm_data)

    def run(self):
        while True:
            self.collect_data()
            self.log_data()
            self.check_alarm()
            time.sleep(10)

    def subscribe(self, subscriber):
        self.__subscribers.append(subscriber)

    def unsubscribe(self, subscriber):
        try:
            self.__subscribers.remove(subscriber)
        except:
            pass

    def notify_subscribers(self, alarm_data):
        for sub in self.__subscribers:
            sub(alarm_data)

if __name__ == "__main__":
    hk = HouseKeeping()
    hk.run()
                                                
