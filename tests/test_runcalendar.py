import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.RunCalendar import RunCalendar

rc = RunCalendar('docs/ALLFDCalendar.txt')
for day in rc.get_next_entries(1):
    for run in rc.get_timetable_for_entry(day):
        print(run)
