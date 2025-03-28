import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.RunCalendar import RunCalendar

from apscheduler.schedulers.background import BackgroundScheduler
import time

scheduler = BackgroundScheduler()

runlist = []
rc = RunCalendar('docs/ALLFDCalendar.txt')
#for day in rc.get_next_entries(1):
for day in rc.get_next_entries():
    for run in rc.get_timetable_for_entry(day):
        scheduler.add_job(print, 'date', run_date=run.start_time)
        runlist.append(run)

#scheduler.print_jobs()
scheduler.start()

sortlist = sorted(runlist, key=lambda x: x.start_time)

for run in sortlist:
    print(run)

time.sleep(1000)
