#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import threading
import logging
import cmd2
import time
from datetime import datetime, timedelta
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.HouseKeeping import HouseKeeping
from lib.RunManager import RunManager
from lib.RunCalendar import RunEntry
from lib.Logger import Logger
from lib.Run import RunType, RunBase
from lib.GpsTime import unix_to_gps
from lib import TimeSync

class App(cmd2.Cmd):

    def __init__(self):
        super().__init__(persistent_history_file='~/.main_history', persistent_history_length=100)

        self.cfg = Configuration()
        self.cfg.read()

        self.identity = self.cfg.parameters['identity']

        self.dc = DeviceCollection()
        self.dc.init(self.cfg)

        Logger.init()

        # FPGA seconds counter used in the shot timestamps: verify / align it before any run
        self.fpga_time_ensure()

        self.hk = HouseKeeping(self.cfg.parameters)
        self.thr_hk = threading.Thread(target=self.hk.run)
        self.thr_hk.start()

        self.rm = RunManager(self.dc, self.hk, self.cfg.parameters)

        self.prompt_styles = {
            'auto': self.identity + ":" + cmd2.style('AUTO', fg=cmd2.Fg.GREEN, bold=True) + "> ",
            'manual': self.identity + ":" + cmd2.style('MANUAL', fg=cmd2.Fg.YELLOW, bold=True) + "> ",
        }
        self.mode = 'auto'

        self.prompt = self.prompt_styles[self.mode]

    # catch CTRL-C to avoid issues with running threads/processes
    def sigint_handler(self, signum, sigframe):
        pass

    def fpga_time_ensure(self):
        logger = logging.getLogger("run")

        def log(level, msg):
            print(f"{level.upper()}: {msg}")
            logger.log(getattr(logging, level.upper()), msg, extra={'classname': 'App'})
        # local PPS first: a force align also increments the seconds counter
        pps_ok = TimeSync.ensure_pps(self.dc.fpga, self.dc.hw.tick_ns, log)
        return TimeSync.ensure(self.dc.fpga, log) and pps_ok

    ## fpga_time ##

    fpga_time_parser = cmd2.Cmd2ArgumentParser()
    fpga_time_parser.add_argument('action', choices=['check', 'align'])

    @cmd2.with_category('System Control')
    @cmd2.with_argparser(fpga_time_parser)
    def do_fpga_time(self, args):
        """check / align the FPGA time: local PPS to the GPS PPS, seconds counter to the host clock"""
        if args.action == 'check':
            off = TimeSync.offset(self.dc.fpga)
            fpga_unix = int(time.time()) + off
            print(f"FPGA {fpga_unix} (GPS {unix_to_gps(fpga_unix)}), offset from host {off} s")
            print(f"local PPS - GPS PPS: {-TimeSync.pps_error_ns(self.dc.fpga, self.dc.hw.tick_ns):+.0f} ns")
            return
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        if self.rm.job_is_running():
            print("E: run in progress")
            return
        self.fpga_time_ensure()

    ## mode ##

    mode_parser = cmd2.Cmd2ArgumentParser()
    mode_parser.add_argument('mode', choices=['auto', 'manual'])

    @cmd2.with_category('System Control')
    @cmd2.with_argparser(mode_parser)
    def do_mode(self, arg):
        """set system mode"""
        if arg.mode == 'manual':
            # disable scheduler
            self.rm.stop_scheduler()
        elif arg.mode == 'auto':
            # enable scheduler
            self.rm.start_scheduler()
        self.mode = arg.mode
        self.prompt = self.prompt_styles[self.mode]
        print(f"mode set to {self.mode}")

    ## start ##
    
    start_parser = cmd2.Cmd2ArgumentParser()
    start_parser.add_argument('runtype', choices=[
        str.lower(RunType.RAMAN.name),
        str.lower(RunType.FD.name),
        str.lower(RunType.TANK.name),
        str.lower(RunType.CALIB.name),
        str.lower(RunType.MOCK.name)])

    @cmd2.with_category('System Control')
    @cmd2.with_argparser(start_parser)
    def do_start(self, arg):
        """start a run"""
        if self.mode == 'auto':
            print("E: set mode to manual")
            return

        if arg.runtype == 'raman':
            run = RunEntry(datetime.now(), RunType.RAMAN, False, False)
        elif arg.runtype == 'fd':
            run = RunEntry(datetime.now(), RunType.FD, False, False)
        elif arg.runtype == 'tank':
            run = RunEntry(datetime.now(), RunType.TANK, False, False)
        elif arg.runtype == 'calib':
            run = RunEntry(datetime.now(), RunType.CALIB, False, False)
        elif arg.runtype == 'mock':
            run = RunEntry(datetime.now(), RunType.MOCK, False, False)
             
        self.rm.submit(run, source='cli')

    ## stop ##
    @cmd2.with_category('System Control')
    def do_stop(self, _):
        """stop a run"""
        if self.rm.job_is_running() == True:
            print(f"run {self.rm.runentry.runtype.name} in progress")
            res = input("do you confirm stop (y/n) ")
            if str.lower(res) == 'y':
                self.rm.stop()
                print("run stopped")
        else:
            print("no run in progress")

    ## kill ##
    @cmd2.with_category('System Control')
    def do_kill(self, _):
        """kill a run"""
        if self.rm.job_is_running() == True:
            print(f"run {self.rm.runentry.runtype.name} in progress")
            res = input("do you confirm kill (y/n) ")
            if str.lower(res) == 'y':
                self.rm.kill()
                print("run killed")
        else:
            print("no run in progress")

    ## status ##
    @cmd2.with_category('System Control')
    def do_status(self, _):
        """get system info"""
        print(f"mode: {self.mode}")
        print(f'scheduler status: {self.rm.print_status()}')
        print(f'next run for auto mode: {self.rm.next_run()}')

    ## calendar ##

    cal_parser = cmd2.Cmd2ArgumentParser()
    cal_subparser = cal_parser.add_subparsers(title='subcommands')

    cal_today_parser = cal_subparser.add_parser("today", help='show next run for today')

    cal_next_parser = cal_subparser.add_parser("next", help='show next number of runs')
    cal_next_parser.add_argument('num', type=int, help='number of runs')

    def caltoday(self, args):
        n = 0
        for i, run in enumerate(self.rm.runlist):
            if run.start_time.day == datetime.now().day and run.start_time.month == datetime.now().month and run.start_time.year == datetime.now().year:
                print(f'{n+1}: {run}')
                n = n + 1
        if n == 0:
            print("no runs for today")

    def calnext(self, args):
        for i, run in enumerate(self.rm.runlist):
            if run.start_time > datetime.now():
                for n, r in enumerate(self.rm.runlist[i:i+args.num]):
                    print(f'{n+1}: {r}')
                break;

    cal_today_parser.set_defaults(func=caltoday)
    cal_next_parser.set_defaults(func=calnext)

    @cmd2.with_category('System Control')
    @cmd2.with_argparser(cal_parser)
    def do_calendar(self, args):
        """get calendar for next runs"""
        func = getattr(args, 'func', None)
        if func is not None:
            func(self, args)
        else:
            self.do_help("cal")

    ## pdu ##

    pdu_parser = cmd2.Cmd2ArgumentParser()
    pdu_subparser = pdu_parser.add_subparsers(title='subcommands')

    pdu_on_parser = pdu_subparser.add_parser("on", help='power on outlet')
    pdu_on_parser.add_argument('num', type=int, help='outlet number')

    pdu_off_parser = pdu_subparser.add_parser("off", help='power off outlet')
    pdu_off_parser.add_argument('num', type=int, help='outlet number')

    pdu_status_parser = pdu_subparser.add_parser("status", help='show pdu status')

    def pduon(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        for k,v in self.dc.outlets.items():
            if v.id == args.num:
                v.on()
                return
        print(f"E: outlet {args.num} not available")

    def pduoff(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        for k,v in self.dc.outlets.items():
            if v.id == args.num:
                v.off()
                return
        print(f"E: outlet {args.num} not available")

    def pdustatus(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        status = ["off", "on"]
        for k,v in self.dc.outlets.items():
            print(f"{v.id} {k} {status[v.status()]}")

    pdu_on_parser.set_defaults(func=pduon)
    pdu_off_parser.set_defaults(func=pduoff)
    pdu_status_parser.set_defaults(func=pdustatus)

    @cmd2.with_category('Instruments Control')
    @cmd2.with_argparser(pdu_parser)
    def do_pdu(self, args):
        """manage pdu outlets"""
        func = getattr(args, 'func', None)
        if func is not None:
            func(self, args)
        else:
            self.do_help("pdu")

    ## quit ##

    @cmd2.with_category('System Control')
    def do_quit(self, _):
        """quit"""
        if self.rm.job_is_running() == True:
            print(f"run in progress - try again later")
            return
        self.hk.close()
        self.thr_hk.join()
        self.rm.close()
        print("Bye!")
        sys.exit(0)

    vertCover_parser = cmd2.Cmd2ArgumentParser()
    vertCover_subparser = vertCover_parser.add_subparsers(title='subcommands', help='open or close vertical cover')

    vertCover_open_parser = vertCover_subparser.add_parser("open", help='Open vertical cover')
    vertCover_close_parser = vertCover_subparser.add_parser("close", help='Close vertical cover')

    def vertCover_open(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.get_outlet("Vert_cover").on()
    
    def vertCover_close(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.get_outlet("Vert_cover").off()

    vertCover_open_parser.set_defaults(func=vertCover_open)
    vertCover_close_parser.set_defaults(func=vertCover_close)

    @cmd2.with_category('Instruments Control')
    @cmd2.with_argparser(vertCover_parser)
    def do_VerticalCover(self, _):
        """manage vertical cover"""
        func = getattr(_, 'func', None)
        if func is not None:
            func(self, _)
        else:
            self.do_help("Vertical Cover open or close")

    
    RamanCover_parser = cmd2.Cmd2ArgumentParser()
    RamanCover_subparser = RamanCover_parser.add_subparsers(title='subcommands')

    RamanCover_open_parser = RamanCover_subparser.add_parser("open", help='Open Raman cover')
    RamanCover_close_parser = RamanCover_subparser.add_parser("close", help='Close Raman cover')
    RamanCover_status_parser = RamanCover_subparser.add_parser("status", help='Status Raman cover')

    def RamanCover_open(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.get_outlet("RAMAN_inst").on()
        time.sleep(1)
        self.dc.get_outlet("RAMAN_cover").on()
        cover_timeout_s = 120
        t = 0
        while self.dc.fpga.read_dio('cover_raman_open') == self.dc.fpga.read_dio('cover_raman_closed'):
            if t >= cover_timeout_s:
                print(f"cover open timeout ({cover_timeout_s}) error")
                return
            time.sleep(1)
            t += 1
    
    def RamanCover_close(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.get_outlet("RAMAN_cover").off()
        time.sleep(1)
        self.dc.get_outlet("RAMAN_inst").off()
        cover_timeout_s = 120
        t = 0
        while self.dc.fpga.read_dio('cover_raman_open') == True:
            if t >= cover_timeout_s:
                print(f"cover close timeout ({cover_timeout_s}) error")
                return
            time.sleep(1)
            t += 1
    
    
    def RamanCover_status(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        print(f"Raman cover open: {self.dc.fpga.read_dio('cover_raman_open')}")
        print(f"Raman cover closed: {self.dc.fpga.read_dio('cover_raman_closed')}")

    RamanCover_open_parser.set_defaults(func=RamanCover_open)
    RamanCover_close_parser.set_defaults(func=RamanCover_close)
    RamanCover_status_parser.set_defaults(func=RamanCover_status)

    @cmd2.with_category('Instruments Control')
    @cmd2.with_argparser(RamanCover_parser)
    def do_RamanCover(self, _):
        """manage raman cover"""
        func = getattr(_, 'func', None)
        if func is not None:
            func(self, _)
        else:
            self.do_help("Raman Cover open, close and status")

    
    laser_parser = cmd2.Cmd2ArgumentParser()
    laser_subparser = laser_parser.add_subparsers(title='subcommands')
    
    lser_init_parser = laser_subparser.add_parser("init", help='initialize laser')
    lser_warm_parser = laser_subparser.add_parser("warm", help='warm laser')
    lser_fire_parser = laser_subparser.add_parser("fire", help='fire mode laser')
    lser_energy_parser = laser_subparser.add_parser("energy", help='set energy laser')
    lser_energy_parser.add_argument('num', type=int, help='energy of the laser')
    lser_checktemp_parser= laser_subparser.add_parser("temps", help='check laser temps')
    
    def laserinit(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.laser.set_mode(qson = 1, dpw = 140)
        
    def laserwarm(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.laser.warmup()
        
    def laserfire(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        if self.dc.laser.fire() != 0:
            print("E: laser not in fire mode (temperature readout failed or out of range, see device.log)")

    def laserenergy(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        self.dc.laser.set_pwdth(args.num)
    
    def lasertemps(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        temps = self.dc.laser.temperature()
        print(f"Laser temps: {temps}")

    lser_init_parser.set_defaults(func=laserinit)
    lser_warm_parser.set_defaults(func=laserwarm)
    lser_fire_parser.set_defaults(func=laserfire)
    lser_energy_parser.set_defaults(func=laserenergy)
    lser_checktemp_parser.set_defaults(func=lasertemps)

    @cmd2.with_category('Instruments Control')
    @cmd2.with_argparser(laser_parser)
    def do_laser(self, _):
        """manage laser"""
        func = getattr(_, 'func', None)
        if func is not None:
            func(self, _)
        else:
            self.do_help("laser init, warm, fire, energy")


    power_parser = cmd2.Cmd2ArgumentParser()
    power_subparser = power_parser.add_subparsers(title='subcommands')
    
    on_power_subparser = power_subparser.add_parser("on", help='initialize system power')
    off_power_subparser = power_subparser.add_parser("off", help='shutdown system power')

    def system_on(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        print("system power on ...")
        self.dc.get_outlet("VXM").on()
        time.sleep(1)
        self.dc.get_outlet("laser").on()
        time.sleep(1)   
        self.dc.get_outlet("radiometer").on()
        print("system power on done")

    def system_off(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        print("system power off ...")
        self.dc.get_outlet("radiometer").off()
        time.sleep(1)
        self.dc.get_outlet("laser").off()
        time.sleep(1)   
        self.dc.get_outlet("VXM").off()
        print("system power off done")

    off_power_subparser.set_defaults(func=system_off)
    on_power_subparser.set_defaults(func=system_on)

    @cmd2.with_category('System Control')
    @cmd2.with_argparser(power_parser)
    def do_system_power(self, _):
        """system power management on/off"""
        func = getattr(_, 'func', None)
        if func is not None:
            func(self, _)
        else:
            self.do_help("system_power on or off")
    

    flipper_parser = cmd2.Cmd2ArgumentParser()
    flipper_subparser = flipper_parser.add_subparsers(title='subcommands')
    
    raman_flipper_subparser = flipper_subparser.add_parser("raman", help='raman flipper control')
    raman_flipper_subparser.add_argument('state', choices=['on', 'off'], help='raman flipper state')
    steering_flipper_subparser = flipper_subparser.add_parser("steering", help='steering flipper control')
    steering_flipper_subparser.add_argument('state', choices=['on', 'off'], help='steering flipper state')

    def raman_flipper(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        if args.state == 'on':
            self.dc.fpga.write_dio('flipper_raman', True)
        else:
            self.dc.fpga.write_dio('flipper_raman', False)
    
    def steering_flipper(self, args):
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        if args.state == 'on':
            self.dc.fpga.write_dio('flipper_steer', True)
        else:
            self.dc.fpga.write_dio('flipper_steer', False)
    
    raman_flipper_subparser.set_defaults(func=raman_flipper)
    steering_flipper_subparser.set_defaults(func=steering_flipper)

    @cmd2.with_category('Instruments Control')
    @cmd2.with_argparser(flipper_parser)
    def do_flipper(self, _):
        """manage flippers"""
        func = getattr(_, 'func', None)
        if func is not None:
            func(self, _)
        else:
            self.do_help("flipper raman or steering on/off")
    
    manual_fire_parser = cmd2.Cmd2ArgumentParser()
    manual_fire_parser.add_argument('num', type=int, help='number of laser shots to fire (1-100000)')  
    manual_fire_parser.add_argument('frequency', type=int, help='frequency of laser shots to fire (Hz) (1-100)')
    
    @cmd2.with_category('Instruments Control')
    @cmd2.with_argparser(manual_fire_parser)
    def do_manual_fire(self, args):
        """manual laser fire"""
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        n_shots = args.num
        if n_shots < 1 or n_shots > 100000:
            print("E: number of shots must be between 1 and 100000")
            return
        frequency = args.frequency
        if frequency < 1 or frequency > 100:
            print("E: frequency must be between 1 and 100 Hz")
            return
        hw = self.dc.hw
        self.dc.fpga.write_register('pps_delay', 0)
        self.dc.fpga.write_bit('laser_en', 1)
        self.dc.fpga.write_bit('timestamp_en', 0)
        self.dc.fpga.write_register('pulse_width', hw.ticks(RunBase.PULSE_WIDTH_S))
        self.dc.fpga.write_register('pulse_energy', hw.ticks(RunBase.PULSE_ENERGY_S))
        self.dc.fpga.write_register('pulse_period', hw.period(1.0 / frequency))
        self.dc.fpga.write_register('shots_num', n_shots)
        print(f"Firing {n_shots} shots at {frequency} Hz ...")
        self.dc.fpga.write_dio('laser_start', 1)
        #print("Manual fire done.")

    ######### system_init
    @cmd2.with_category('System Control')
    def do_system_init(self, _):
        """system initialization"""
        if self.mode == 'auto':
            print("E: set mode to manual")
            return
        print("system initialization ...")
        
        print("Radiometer setup ...")
        self.dc.get_radiometer('Rad1').setup()
        self.dc.get_radiometer('Rad3').setup()

        print("Laser setup ...")
        self.dc.laser.set_mode(qson = 1, dpw = 140)
        self.dc.laser.warmup()

        print("Flippers and motors setup ...")
        self.dc.fpga.write_dio('flipper_steer', False)
        self.dc.fpga.write_dio('flipper_raman', False)

        print("Motors homing ...")
        self.dc.get_motor("UpEastWest").init()  
        self.dc.get_motor("UpEastWest").move_Neg0()  
        self.dc.get_motor("UpEastWest").move_Neg0()  
        self.dc.get_motor("UpEastWest").set_ABSzero()

        self.dc.get_motor("UpNorthSouth").init()  
        self.dc.get_motor("UpNorthSouth").move_Neg0()  
        self.dc.get_motor("UpNorthSouth").move_Neg0()  
        self.dc.get_motor("UpNorthSouth").set_ABSzero()

        self.dc.get_motor("LwNorthSouth").init() 
        self.dc.get_motor("LwNorthSouth").move_Neg0()
        self.dc.get_motor("LwNorthSouth").move_Neg0()
        self.dc.get_motor("LwNorthSouth").set_ABSzero()

        self.dc.get_motor("LwPolarizer").init() 
        self.dc.get_motor("LwPolarizer").move_Neg0()
        self.dc.get_motor("LwPolarizer").move_Neg0()
        self.dc.get_motor("LwPolarizer").set_ABSzero()
        print("system initialization done.")



app = App()
app.cmdloop()
