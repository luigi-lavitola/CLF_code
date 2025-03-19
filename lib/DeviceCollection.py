import os
import sys
import serial
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RPC import RPCDevice
from lib.VXM import VXM
from lib.Radiometer import Radiometer3700, RadiometerOphir
from lib.Centurion import Centurion
from lib.FPGADevice import FPGADevice

class DeviceCollection:
    def __init__(self):
        self.serials = {}
        self.outlets = {}
        self.motors = {}
        self.radiometers = {}
        self.fpga = FPGADevice("/dev/runcontrol")
        self.laser = Centurion("/dev/ttyr01")

    def init(self, cfg):
        # outlets
        for oname, oparams in cfg.outlets.items():
            port_params = cfg.get_port_params(oparams['port'])
            self.add_outlet(oparams['id'], oname, **port_params)

        # motors
        for mname, mparams in cfg.motors.items():
            port_params = cfg.get_port_params(mparams['port'])
            self.add_motor(mparams['id'], mname, **port_params)

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

    def add_motor(self, id, name, port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1):
        if(self.serials.get(port, None) == None):
            params = locals()
            params.pop('self')
            params.pop('id')
            params.pop('name')
            self.serials[port] = VXM(**params)

        vxm = self.serials[port]
        self.motors[name] = vxm.add_motor(id, name)

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
