#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import threading 
import cmd2
from datetime import datetime, timedelta
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.HouseKeeping import HouseKeeping
from lib.RunManager import RunManager
from lib.RunCalendar import RunEntry
from lib.Logger import Logger
from lib.Run import RunType

class App(cmd2.Cmd):

    def __init__(self):
        super().__init__(persistent_history_file='~/.main_history', persistent_history_length=100)

        self.cfg = Configuration()
        self.cfg.read()

        self.dc = DeviceCollection()
        self.dc.init(self.cfg)

        #Logger.init()

        self.hk = HouseKeeping()
        self.thr_hk = threading.Thread(target=self.hk.run)
        self.thr_hk.start()

        self.rm = RunManager(self.dc, self.hk)

        self.prompt_styles = {
            'auto': "CLF:" + cmd2.style('AUTO', fg=cmd2.Fg.GREEN, bold=True) + "> ",
            'manual': "CLF:" + cmd2.style('MANUAL', fg=cmd2.Fg.YELLOW, bold=True) + "> ",
        }
        self.mode = 'auto'

        self.prompt = self.prompt_styles[self.mode]

    # catch CTRL-C to avoid issues with running threads/processes
    def sigint_handler(self, signum, sigframe):
        pass

    ## mode ##

    mode_parser = cmd2.Cmd2ArgumentParser()
    mode_parser.add_argument('mode', choices=['auto', 'manual'])

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
        str.lower(RunType.CELESTE.name),
        str.lower(RunType.CALIB.name),
        str.lower(RunType.MOCK.name)])

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
        elif arg.runtype == 'celeste':
            run = RunEntry(datetime.now(), RunType.CELESTE, False, False)
        elif arg.runtype == 'calib':
            run = RunEntry(datetime.now(), RunType.CALIB, False, False)
        elif arg.runtype == 'mock':
            run = RunEntry(datetime.now(), RunType.MOCK, False, False)
             
        self.rm.submit(run, source='cli')
            
    ## status ##

    def do_status(self, _):
        """get system info"""
        print(f"mode: {self.mode}")
        print(f'scheduler status: {self.rm.print_status()}')
        print(f'next run for auto mode: {self.rm.next_run()}')

    ## quit ##

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

app = App()
app.cmdloop()
