
import os
import sys
import gps
import time
import datetime
import logging
import threading
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

        self.gpsd = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
        self.gps_thr = None

        self.log = logging.getLogger("housekeeping")
        self.log.setLevel(logging.INFO)

        log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_handler = TimedRotatingFileHandler('logs/hk.log', when='midnight', 
            atTime=datetime.time(hour=18, minute=0))
        log_handler.setFormatter(log_formatter)
        self.log.addHandler(log_handler)

        self.csv = logging.getLogger("csv_housekeeping")
        self.csv.setLevel(logging.INFO)
        csv_formatter = logging.Formatter('%(asctime)s%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        csv_handler = TimedRotatingFileHandler('logs/hk.csv', when='midnight', 
            atTime=datetime.time(hour=18, minute=0))
        csv_handler.setFormatter(csv_formatter)
        self.csv.addHandler(csv_handler)

        try:
            self.fpga = FPGADevice("/dev/runcontrol")
        except:
            self.fpga = FPGADevice.getInstance()

        self.tcont.config_channel(2, SENSOR_TYPE__SENSE_RESISTOR |
            (10000 * 1024) << SENSE_RESISTOR_VALUE_LSB)

        for ch in [4, 6, 8, 10, 12, 14, 16, 18, 20]:
            self.tcont.config_channel(ch, SENSOR_TYPE__THERMISTOR_44006_10K_25C |
                THERMISTOR_RSENSE_CHANNEL__2 |
                THERMISTOR_DIFFERENTIAL |
                THERMISTOR_EXCITATION_MODE__SHARING_ROTATION |
                THERMISTOR_EXCITATION_CURRENT__AUTORANGE)

        self.data = [
            { "dev": "tla", "name": "battery1", "channel": 0, "value": 0, 
                "unit": "V", "coeff": 0.012698329443235162, "min": 11.5, "max": 16, "alarm": False},
            { "dev": "tla", "name": "battery2", "channel": 1, "value": 0, 
                "unit": "V", "coeff": 0.012857486052905534, "min": 11.5, "max": 16, "alarm": False},
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
            { "dev": "gps", "name": "gps_fix", "value": True, "alarm": False, "info": "" },
        ]
        
        self.gps_fix_str = [ "unknown", "no fix", "2D", "3D" ]

        self.running = False
        self.alarm_data = []

    def collect_gps(self):
        while self.running:
            self.gpsd.next()

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
            elif d['dev'] == 'gps':
                if d['name'] == 'gps_fix':
                    d['value'] = self.gpsd.fix.mode > 1
                    d['info'] = self.gps_fix_str[self.gpsd.fix.mode]

    def log_data(self):
        s = ''
        csv_row = f',{int(time.time())}'
        for d in self.data:
            s += f" {d['name']}={d['value']}[{d.get('unit', '')}]" 
            csv_row += f",{d['value']}"
        self.log.info(s)
        self.csv.info(csv_row)

    def check_alarm(self):
        self.alarm_data = []
        for d in self.data:
            if d.get('alarm', None) is not None:
                if d['dev'] == 'tla':
                    if (d['value'] < d['min']) or (d['value'] > d['max']):
                        d['alarm'] = True
                        self.alarm_data.append(d)
                    else:
                        d['alarm'] = False
                elif d['dev'] == 'dio':
                    if d['name'] == 'rain':
                        if d['value'] or d['error']:
                            d['alarm'] = True
                            self.alarm_data.append(d)
                        else:
                            d['alarm'] = False
                elif d['dev'] == 'gps':
                    if d['name'] == 'gps_fix':
                        d['alarm'] = self.gpsd.fix.mode <= 1

        #FIXME
        #if len(self.alarm_data):
        #    self.notify_subscribers(self.alarm_data)

    def get_alarm(self):
        return self.alarm_data

    def run(self):
        self.running = True
        self.gps_thr = threading.Thread(target=self.collect_gps)
        self.gps_thr.start()
        while True:
            self.collect_data()
            self.log_data()
            self.check_alarm()
            for _ in range(10):
                if self.running == False:
                    return
                time.sleep(1)

    def close(self):
        self.running = False
        self.gps_thr.join()

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
                                                
