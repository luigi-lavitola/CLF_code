#!/usr/bin/env python3

import sys
import os
import signal
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import threading 
import cmd2
from datetime import datetime
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.HouseKeeping import HouseKeeping
from lib.RunManager import RunManager, RunType
from lib.RunCalendar import RunEntry

class App(cmd2.Cmd):

    def __init__(self):
        super().__init__(persistent_history_file='~/.main_history', persistent_history_length=100)

        self.cfg = Configuration()
        self.cfg.read()

        self.dc = DeviceCollection()
        self.dc.init(self.cfg)

        self.hk = HouseKeeping()
        self.thr_hk = threading.Thread(target=self.hk.run)
        self.thr_hk.start()

        self.rm = RunManager(self.dc, self.hk)

        self.mode = "auto"

        self.prompt = f"CLF:{self.mode}> "

    ## mode ##

    mode_parser = cmd2.Cmd2ArgumentParser()
    mode_parser.add_argument('mode', choices=['auto', 'manual'])

    @cmd2.with_argparser(mode_parser)
    def do_mode(self, arg):
        """set system mode"""
        if arg.mode == 'manual':
            # disable scheduler
            pass
        elif arg.mode == 'auto':
            # enable scheduler
            pass
        self.mode = arg.mode
        self.prompt = f"CLF:{self.mode}> "
        print(f"mode set to {self.mode}")

    ## start ##
    
    start_parser = cmd2.Cmd2ArgumentParser()
    start_parser.add_argument('runtype', choices=['raman', 'clf', 'mock'])

    @cmd2.with_argparser(start_parser)
    def do_start(self, arg):
        """start a run"""
        if self.mode == 'auto':
            print("E: set mode to manual")
            return

        run = RunEntry(datetime.now(), arg.runtype, False, False)
        self.rm.submit(run, source='cli')
            
    ## status ##

    def do_status(self, _):
        """get system info"""
        print(f"mode: {self.mode}")

    ## quit ##

    def do_quit(self, _):
        """quit"""
        # check if manual run is in progress
        self.hk.close()
        self.thr_hk.join()
        self.rm.close()
        print("Bye!")
        sys.exit(0)

# catch CTRL-C to avoid issues with running threads/processes
def signal_handler(sig, frame):
    pass

signal.signal(signal.SIGINT, signal_handler)

app = App()
app.cmdloop()
