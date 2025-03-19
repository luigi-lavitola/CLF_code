#!/usr/bin/env python3
# coding=utf-8

import argparse
import os
import time
import sys
import cmd2
import functools
import getpass
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


        self.prompt = cmd2.ansi.style("clf> ", fg=cmd2.fg.green)
        self.intro = cmd2.ansi.style("Welcome to the CLF CLI, type help for the list of commands", fg=cmd2.fg.red)

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
        dc.get_outlet("Raman_cover").on()

    @cmd2.with_category("RPC command")
    def do_close_Raman_cover(self, args: argparse.Namespace) -> None:
        dc.get_outlet("Raman_cover").off()


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
    



if __name__ == '__main__':
   parser = argparse.ArgumentParser()
   
   args = parser.parse_args()

   app = CLF_app(args)
   app.cmdloop()

