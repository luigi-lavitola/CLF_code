#!/usr/bin/env python3
# coding=utf-8

import argparse
import os
import time
import sys
import cmd2
import functools
import getpass
import time
import numpy as np
from cmd2.table_creator import (
    Column,
    SimpleTable,
    HorizontalAlignment
)
from typing import (
    List,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RPC import RPCDevice
from lib.Centurion import Centurion
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.Radiometer import Radiometer3700, RadiometerOphir

cfg = Configuration()
cfg.read()

dc = DeviceCollection()

class CLF_app(cmd2.Cmd):

    def __init__(self, param):
        super().__init__(allow_cli_args=False)
        del cmd2.Cmd.do_edit
        del cmd2.Cmd.do_macro
        del cmd2.Cmd.do_run_pyscript
        del cmd2.Cmd.do_shell
        del cmd2.Cmd.do_shortcuts


        self.prompt = cmd2.ansi.style("clf> ")
        self.intro = cmd2.ansi.style("Welcome to the CLF CLI, type help for the list of commands")

        cmd2.categorize(
            (cmd2.Cmd.do_alias, cmd2.Cmd.do_help, cmd2.Cmd.do_history, cmd2.Cmd.do_quit, cmd2.Cmd.do_set, cmd2.Cmd.do_run_script),
            "General commands" 
        )

    
    ########add functions##############

    ##### RPC Functions ############
    plugs=[]
    @cmd2.with_category("RPC command")
    def do_rpc_init(self, args: argparse.Namespace) -> None:
        for oname, oparams in cfg.outlets.items():
            port_params = cfg.get_port_params(oparams['port'])
            dc.add_outlet(oparams['id'], oname,
                port=port_params['port'],
                baudrate=port_params['baudrate'],
                bytesize=port_params['bytesize'],
                parity=port_params['parity'],
                stopbits=port_params['stopbits'],
                timeout=port_params['timeout']
            )
            self.plugs.append(oname)
        

    rpc_parser = argparse.ArgumentParser()
    rpc_parser.add_argument('value', type=str, help='name of plug', choices=plugs)
    rpc_parser.add_argument('status', type=str, help='status of the plug on off', choices=['on','off'])

    @cmd2.with_argparser(rpc_parser)
    @cmd2.with_category("RPC command")
    def do_rpc(self, args: argparse.Namespace) -> None:
        
        if args.status == 'on':
            print('on to plug ' + args.value)
            ind=self.plugs.index(args.value)
            dc.get_outlet(str(self.plugs[ind])).on() 
            
        else:
            print('off to plug ' + args.value )
            ind=self.plugs.index(args.value)
            dc.get_outlet(str(self.plugs[ind])).off() 

    @cmd2.with_category("RPC command")
    def do_on_instruments(self, args: argparse.Namespace) -> None:
        dc.get_outlet("radiometer").on()
        dc.get_outlet("laser").on()
        dc.get_outlet("VXM").on()
    
    @cmd2.with_category("RPC command")
    def do_off_instruments(self, args: argparse.Namespace) -> None:
        dc.get_outlet("radiometer").off()
        dc.get_outlet("laser").off()
        dc.get_outlet("VXM").off()

    
    @cmd2.with_category("RPC command")
    def do_on_raman(self, args: argparse.Namespace) -> None:
        dc.get_outlet("RAMAN_inst").on()
    
    @cmd2.with_category("RPC command")
    def do_off_raman(self, args: argparse.Namespace) -> None:
        dc.get_outlet("RAMAN_inst").off()

    @cmd2.with_category("RPC command")
    def do_open_vert_cover(self, args: argparse.Namespace) -> None:
        dc.get_outlet("Vert_cover").on()
    
    @cmd2.with_category("RPC command")
    def do_close_vert_cover(self, args: argparse.Namespace) -> None:
        dc.get_outlet("Vert_cover").off()
    
    @cmd2.with_category("RPC command")
    def do_open_Raman_cover(self, args: argparse.Namespace) -> None:
        dc.get_outlet("RAMAN_inst").on()
        time.sleep(1)
        dc.get_outlet("RAMAN_cover").on()

    @cmd2.with_category("RPC command")
    def do_close_Raman_cover(self, args: argparse.Namespace) -> None:
        dc.get_outlet("RAMAN_cover").off()


    ######### LASER FUNCTIONS ##################
    @cmd2.with_category("laser command")
    def do_lsr_connect(self, args: argparse.Namespace) -> None:
        self.laser = Centurion("/dev/ttyr01")

    @cmd2.with_category("laser command")
    def do_lsr_close_conn(self, args: argparse.Namespace) -> None:
        del self.laser 

    @cmd2.with_category("laser command")
    def do_lsr_init(self, args: argparse.Namespace) -> None:
        self.laser.set_mode(100, 1, 1, 1, 1, 1, dpw = 140, qsdelay = 145)

    @cmd2.with_category("laser command")
    def do_lsr_fire(self, args: argparse.Namespace) -> None:
        self.laser.fire()

    lsr_energy_parser = argparse.ArgumentParser()
    lsr_energy_parser.add_argument('value', type=int, help='energy of the laser shot in us')
    @cmd2.with_argparser(lsr_energy_parser)
    @cmd2.with_category("laser command")
    def do_lsr_energy(self, args: argparse.Namespace) -> None:
        self.laser.set_pwdth(args.value)
    
    @cmd2.with_category("laser command")
    def do_lsr_checktemps(self, args: argparse.Namespace) -> None:
        self.laser.check_temps()
    
    @cmd2.with_category("laser command")
    def do_lsr_warmup(self, args: argparse.Namespace) -> None:
        self.laser.warmup()

    ######### RADIOMETER FUNCTIONS ##################
    @cmd2.with_category("radiometer command")
    def do_rad1_connect(self, args: argparse.Namespace) -> None:
        rad1= Radiometer3700("/dev/ttyr02")
        rad1.info()
        rad1.setup()
    
    @cmd2.with_category("radiometer command")
    def do_rad2_connect(self, args: argparse.Namespace) -> None:
        rad2= Radiometer3700("/dev/ttyr04")
        rad2.info()
        rad2.setup()

    @cmd2.with_category("radiometer command")
    def do_rad3_connect(self, args: argparse.Namespace) -> None:
        rad3= RadiometerOphir("/dev/ttyr05")
        rad3.info()
        rad3.set("$DU", 1)


    ######### MOTOR FUNCTIONS ##################
    motors=[]
    @cmd2.with_category("VXM commands")
    def do_VXM_init(self, args: argparse.Namespace) -> None:
        for mname, mparams in cfg.motors.items():
            port_params = cfg.get_port_params(mparams['port'])
            dc.add_motor(mparams['id'], mname,
                port=port_params['port'],
                baudrate=port_params['baudrate'],
                bytesize=port_params['bytesize'],
                parity=port_params['parity'],
                stopbits=port_params['stopbits'],
                timeout=port_params['timeout']
            )
            self.motors.append(mname)
        print(self.motors)

    @cmd2.with_category("VXM commands")
    def do_VXM_config(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").set_model(1)
        dc.get_motor("UpNorthSouth").set_acc(2000)
        dc.get_motor("UpEastWest").set_model(1)
        dc.get_motor("UpEastWest").set_acc(2000)
        dc.get_motor("LwNorthSouth").set_model(1)
        dc.get_motor("LwNorthSouth").set_acc(2000)
        dc.get_motor("LwPolarizer").set_model(1)
        dc.get_motor("LwPolarizer").set_acc(2000)

    @cmd2.with_category("VXM commands")
    def do_VXM_ECAL_RAD3(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").move_ABS(33250)
        dc.get_motor("UpEastWest").move_ABS(4470)
    
    @cmd2.with_category("VXM commands")
    def do_VXM_home_UP(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").move_ABS0()
        dc.get_motor("UpEastWest").move_ABS0()
    
    @cmd2.with_category("VXM commands")
    def do_VXM_home_LW(self, args: argparse.Namespace) -> None:
        dc.get_motor("LwNorthSouth").move_ABS0()
        dc.get_motor("LwPolarizer").move_ABS0()

    @cmd2.with_category("VXM commands")
    def do_VXM_move(self, args: argparse.Namespace) -> None:
        ind=self.motors.index(args.motor)
        dc.get_motor(str(self.motors[ind])).move_ABS(args.position)
    
    @cmd2.with_category("VXM commands")
    def do_VXM_position_rad2(self, args: argparse.Namespace) -> None:
        dc.get_motor("UpNorthSouth").move_ABS(1300)
        dc.get_motor("UpEastWest").move_ABS(20200)
    
    @cmd2.with_category("VXM commands")
    def do_VXM_position_pol(self, args: argparse.Namespace) -> None:
        dc.get_motor("LwNorthSouth").move_ABS(18900)

    polarizer_parser = argparse.ArgumentParser()
    polarizer_parser.add_argument('degree', type=int, help='degree of the polarizer')
    @cmd2.with_category("VXM commands")
    def do_VXM_pol_rotate(self, args: argparse.Namespace) -> None:
        print(f"ROTATING POLARIZER IN ANGLE {self.polarizer_parser.degree*80}°:STARTING")
        dc.get_motor("LwPolarizer").move_ABS(self.polarizer_parser.degree)
        print(f"ROTATING POLARIZER IN ANGLE {self.polarizer_parser.degree*80}°:COMPLETE")

    @cmd2.with_category("VXM commands")
    def do_zero_pol(self, args: argparse.Namespace) -> None:
        dc.get_motor("LwPolarizer").move_ABS0()

    @cmd2.with_category("VXM commands")
    def do_init_SteerCover(self, args: argparse.Namespace) -> None:
        dc.get_motor("Cover").set_model(1)
        dc.get_motor("Cover").set_acc(200)

    @cmd2.with_category("VXM commands")
    def do_open_SteerCover(self, args: argparse.Namespace) -> None:
        dc.get_motor("Cover").move_BWD(25000)

    @cmd2.with_category("VXM commands")
    def do_close_SteerCover(self, args: argparse.Namespace) -> None:
        dc.get_motor("Cover").move_FWD(25500)
    


    ######### RunControl FUNCTIONS ##################
    @cmd2.with_category("RunControl commands")
    def do_PowerOn(self, args: argparse.Namespace) -> None:
        print("turn on inverter... ")
        dc.fpga.write_dio('inverter', True)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_PowerOff(self, args: argparse.Namespace) -> None:
        print("turn off inverter... ")
        dc.fpga.write_dio('inverter', False)
        print("done")
    


    rc_parser = argparse.ArgumentParser()
    rc_parser.add_argument('status', type=str, help='status of the bit on off', choices=['on','off'])
    @cmd2.with_argparser(rc_parser)
    @cmd2.with_category("RunControl commands")
    def do_Raman_beam(self, args: argparse.Namespace) -> None:
        if args.status == 'on':
            print("turn on Raman beam... ")
            dc.fpga.write_dio('flipper_raman', True)
            print("done")
        else:
            print("turn off Raman beam... ")
            dc.fpga.write_dio('flipper_raman', False)
            print("done")

    @cmd2.with_category("RunControl commands")
    def do_check_rain(self, args: argparse.Namespace) -> None:
        print("check rain... ")
        if dc.fpga.read_dio('rain') and (not dc.fpga.read_dio('norain')):
            print("It's raining")   
        else:
            print("It's not raining")
    
    @cmd2.with_category("RunControl commands")
    def do_check_pps(self, args: argparse.Namespace) -> None:
        print("check pps... ")
        if dc.fpga.read_dio('pps_ok'):
            print("PPS is ok")   
        else:
            print("PPS is not ok")
    
    @cmd2.with_category("RunControl commands")
    def do_check_jc_lock(self, args: argparse.Namespace) -> None:
        print("check JC lock... ")
        if dc.fpga.read_dio('jc_lock'):
            print("JC is locked")   
        else:
            print("JC is not locked")
    
    @cmd2.with_category("RunControl commands")
    def do_check_vcxo_lock(self, args: argparse.Namespace) -> None:
        print("check VCXO lock... ")
        if dc.fpga.read_dio('vcxo_lock'):
            print("VCXO is locked")   
        else:
            print("VCXO is not locked")

    @cmd2.with_category("RunControl commands")
    def do_force_PPS_align(self, args: argparse.Namespace) -> None:
        print("force align... ")
        dc.fpga.write_dio('force_align', True)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_EN_Laser(self, args: argparse.Namespace) -> None:
        print("Enable Laser Controller... ")
        dc.fpga.write_dio('laser_en', True)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_DIS_Laser(self, args: argparse.Namespace) -> None:
        print("Disable Laser Controller... ")
        dc.fpga.write_dio('laser_en', False)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_ON_flipper_steer(self, args: argparse.Namespace) -> None:
        print("ON flipper steer... ")
        dc.fpga.write_dio('flipper_steer', True)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_OFF_flipper_steer(self, args: argparse.Namespace) -> None:
        print("OFF flipper steer... ")
        dc.fpga.write_dio('flipper_steer', False)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_ON_flipper_atten(self, args: argparse.Namespace) -> None:
        print("ON flipper atten... ")
        dc.fpga.write_dio('flipper_atten', True)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_OFF_flipper_atten(self, args: argparse.Namespace) -> None:
        print("OFF flipper atten... ")
        dc.fpga.write_dio('flipper_atten', False)
        print("done")
    
    @cmd2.with_category("RunControl commands")
    def do_check_cover_raman(self, args: argparse.Namespace) -> None:
        print("check Raman cover... ")
        if dc.fpga.read_dio('cover_raman_closed') and (not dc.fpga.read_dio('cover_raman_open')):
            print("Raman cover is closed")   
        else:
            print("Raman cover is open")
    
    @cmd2.with_category("RunControl commands")
    def do_check_cover_steer(self, args: argparse.Namespace) -> None:
        print("check Steer cover... ")
        if dc.fpga.read_dio('cover_steer_closed') and (not dc.fpga.read_dio('cover_steer_open')):
            print("Steer cover is closed")   
        else:
            print("Steer cover is open")
    
    @cmd2.with_category("RunControl commands")
    def do_align_UnixTime(self, args: argparse.Namespace) -> None:
        timeout = int(time.time()) + 1.5
        while True:
            ts = time.time()
            if ts > timeout:
                unix_time = int(ts)#int(time.time())
                print("align UnixTime... ")
                dc.fpga.write_register('arm_unixtime', int(time.time()))
                print("done")

    @cmd2.with_category("RunControl commands")
    def do_check_UnixTime(self, args: argparse.Namespace) -> None:
        print("check UnixTime... ")
        print(f"UnixTime : {int(time.time())}, FPGA time: {dc.fpga.read_register('unixtime')}")
    
    rc_parser = argparse.ArgumentParser()
    rc_parser.add_argument('value', type=int, help='Delay of shot from the PPS (ms)')
    @cmd2.with_argparser(rc_parser)
    @cmd2.with_category("RunControl commands")
    def do_set_PPS_Delay(self, args: argparse.Namespace) -> None:
        dc.fpga.write_register('pps_delay', args.value*10e5)
    
    rc_parser = argparse.ArgumentParser()
    rc_parser.add_argument('value', type=int, help='Laser pulse width (us), must be more than 50 us')
    @cmd2.with_argparser(rc_parser)
    @cmd2.with_category("RunControl commands")
    def do_set_Pulse_width(self, args: argparse.Namespace) -> None:
        dc.fpga.write_register('pulse_width', args.value*100)
    
    rc_parser = argparse.ArgumentParser()
    rc_parser.add_argument('value', type=int, help='Laser pulse period (ms), 1000 ms for 1 Hz and 10 ms for 100 Hz')
    @cmd2.with_argparser(rc_parser)
    @cmd2.with_category("RunControl commands")
    def do_set_Pulse_period(self, args: argparse.Namespace) -> None:
        dc.fpga.write_register('pulse_period', args.value*10e5)

    rc_parser = argparse.ArgumentParser()
    rc_parser.add_argument('value', type=int, help='Number of shots to be fired')
    @cmd2.with_argparser(rc_parser)
    @cmd2.with_category("RunControl commands")
    def do_set_Pulse_Number(self, args: argparse.Namespace) -> None:
        dc.fpga.write_register('shots_num', args.value)
    
    rc_parser = argparse.ArgumentParser()
    rc_parser.add_argument('value', type=int, help='Pulse energy (us), for 140 us sets 174 us, while for 100 us sets 164')
    @cmd2.with_argparser(rc_parser)
    @cmd2.with_category("RunControl commands")
    def do_set_Pulse_energy(self, args: argparse.Namespace) -> None:
        dc.fpga.write_register('pulse_energy', args.value*10e5)

    @cmd2.with_category("RunControl commands")
    def do_FIRE(self, args: argparse.Namespace) -> None:
        dc.fpga.write_dio('laser_en', 1)
        dc.fpga.write_dio('laser_start', 1)
    
    @cmd2.with_category("RunControl commands")
    def do_stop_FIRE(self, args: argparse.Namespace) -> None:
        dc.fpga.write_dio('laser_en', 0)

        










if __name__ == '__main__':
   parser = argparse.ArgumentParser()
   
   args = parser.parse_args()

   app = CLF_app(args)
   app.cmdloop()

