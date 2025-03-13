import os
import sys
import serial
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RPC import RPCDevice
from lib.VXM import VXM
from lib.FPGADevice import FPGADevice

class DeviceCollection:
    def __init__(self):
        self.serials = {}
        self.outlets = {}
        self.motors = {}
        self.fpga = FPGADevice("/dev/runcontrol")

    def init(self, cfg):
        # outlets
        for oname, oparams in cfg.outlets.items():
            port_params = cfg.get_port_params(oparams['port'])
            self.add_outlet(oparams['id'], oname,
                port=port_params['port'],
                speed=port_params['speed'],
                bytesize=port_params['bytesize'],
                parity=port_params['parity'],
                stopbits=port_params['stopbits'],
                timeout=port_params['timeout']
            )

        # motors
        for mname, mparams in cfg.motors.items():
            port_params = cfg.get_port_params(mparams['port'])
            self.add_motor(mparams['id'], mname,
                port=port_params['port'],
                speed=port_params['speed'],
                bytesize=port_params['bytesize'],
                parity=port_params['parity'],
                stopbits=port_params['stopbits'],
                timeout=port_params['timeout']
            )

    def add_outlet(self, id, name, port, speed=115200, bytesize=8, parity='N', stopbits=1, timeout=1):
        if(self.serials.get(port, None) == None):
            s = serial.Serial(
                port=port, 
                baudrate=speed, 
                bytesize=bytesize, 
                parity=parity,
                stopbits = stopbits,
                timeout = timeout)
            self.serials[port] = RPCDevice(s)

        rpc = self.serials[port]
        self.outlets[name] = rpc.add_outlet(id, name)

    def get_outlet(self, name):
        return self.outlets[name]

    def add_motor(self, id, name, port, speed=115200, bytesize=8, parity='N', stopbits=1, timeout=1):
        if(self.serials.get(port, None) == None):
            s = serial.Serial(
                port=port, 
                baudrate=speed, 
                bytesize=bytesize, 
                parity=parity,
                stopbits = stopbits,
                timeout = timeout)
            self.serials[port] = VXM(s)

        vxm = self.serials[port]
        self.motors[name] = vxm.add_motor(id, name)

    def get_motor(self, name):
        return self.motors[name]

    def __repr__(self):
        return f'{self.outlets}'

if __name__ == "__main__":
    dc = DeviceCollection()

    dc.add_outlet(0, "PC", "/dev/ttyUSB0")
    dc.add_outlet(1, "RAMAN1", "/dev/ttyUSB0")
    print(dc)

    dc.get_outlet("PC").on()
    dc.get_outlet("RAMAN1").on()

