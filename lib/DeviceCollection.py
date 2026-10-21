import os
import sys
import serial
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RPC import RPCDevice
from lib.VXM import VXM
from lib.Radiometer import Radiometer3700, RadiometerOphir
from lib.Centurion import Centurion
from lib.FPGADevice import FPGADevice
from lib.FPGAData import FPGAData
from lib.Hardware import get_profile, check_firmware

class DeviceCollection:
    def __init__(self):
        self.serials = {}
        self.outlets = {}
        self.motors = {}
        self.radiometers = {}
        self.fpga = FPGADevice("/dev/runcontrol")
        self.laser = Centurion("/dev/ttyr01")
        self.data = FPGAData("/dev/data0")

    def init(self, cfg):
        # hardware profile: clock for the timestamp conversion, firmware version check
        self.hw = get_profile(cfg.parameters)
        self.data.tick_ns = self.hw.tick_ns
        check_firmware(self.fpga, self.hw)

        # outlets
        for oname, oparams in cfg.outlets.items():
            port_params = cfg.get_port_params(oparams['port'])
            self.add_outlet(oparams['id'], oname, **port_params)

        # motors
        for mname, mparams in cfg.motors.items():
            port_params = cfg.get_port_params(mparams['port'])
            ecal_position = mparams.get('ecal_position', 0)
            pcal_position = mparams.get('pcal_position', 0)
            self.add_motor(mparams['id'], mname, ecal_position, pcal_position, **port_params)

        # radiometers 
        for rname, rparams in cfg.radiometers.items():
            port_params = cfg.get_port_params(rparams['port'])
            self.add_radiometer(rname, rparams['model'], **port_params)

    def add_outlet(self, id, name, port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1):
        if(self.serials.get(port, None) == None):
            params = locals()
            params.pop('self')
            params.pop('id')
            params.pop('name')
            self.serials[port] = RPCDevice(**params)

        rpc = self.serials[port]
        self.outlets[name] = rpc.add_outlet(id, name)

    def get_outlet(self, name):
        return self.outlets[name]

    def add_motor(self, id, name, ecal_position, pcal_position, port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1):
        if(self.serials.get(port, None) == None):
            params = locals()
            params.pop('self')
            params.pop('id')
            params.pop('name')
            params.pop('ecal_position')
            params.pop('pcal_position')
            self.serials[port] = VXM(**params)

        vxm = self.serials[port]
        self.motors[name] = vxm.add_motor(id, name, ecal_position, pcal_position)

    def get_motor(self, name):
        return self.motors[name]

    def add_radiometer(self, name, model, port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1):
        if(self.serials.get(port, None) == None):
            params = locals()
            params.pop('self')
            params.pop('name')
            params.pop('model')
            if model == "3700":
                self.serials[port] = Radiometer3700(**params)
            elif str.lower(model) == "ophir":
                self.serials[port] = RadiometerOphir(**params)

        self.radiometers[name] = self.serials[port]

    def get_radiometer(self, name):
        return self.radiometers[name]

    def __repr__(self):
        return f'{self.outlets}'
