import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RunCalendar import RunCalendar
import time

runlist = []
rc = RunCalendar('docs/ALLFDCalendar.txt')
#for day in rc.get_next_entries(1):
for day in rc.get_next_entries():
    for run in rc.get_timetable_for_entry(day):
        runlist.append(run)

sortlist = sorted(runlist, key=lambda x: x.start_time)

for run in sortlist:
    print(run)

time.sleep(1000)
