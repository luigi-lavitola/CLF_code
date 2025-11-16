import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RunCalendar import RunCalendar
from lib.Configuration import Configuration
import time
import datetime

cfg = Configuration()
cfg.read()

runlist = []
rc = RunCalendar('docs/ALLFDCalendar.txt', cfg.parameters)
for day in rc.get_next_entries():
    for run in rc.get_timetable_for_entry(day):
        runlist.append(run)

sortlist = sorted(runlist, key=lambda x: x.start_time)

runlist = []

### print n runs starting from now ###

selruns = []
nrun = 15

for i, run in enumerate(sortlist):
    if run.start_time > datetime.datetime.now():
        selruns = sortlist[i:i+nrun]
        break;

print(selruns)
print(len(selruns))

### print run list for today ###

selruns = []

for run in sortlist:
    if run.start_time > datetime.datetime.now():
        if run.start_time.day == datetime.datetime.now().day:
            selruns.append(run)

print(selruns)
print(len(selruns))
