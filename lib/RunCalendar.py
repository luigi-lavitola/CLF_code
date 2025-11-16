from datetime import datetime, timedelta
from dataclasses import dataclass
from lib.Run import RunType

@dataclass
class CalendarEntry:
    start_date: datetime
    end_date: datetime
    has_fd_run: bool

    def __str__(self):
        return f'has_fd_run: {self.has_fd_run},start_date: {self.start_date}, end_date: {self.end_date}'

@dataclass
class RunEntry:
    start_time: datetime
    runtype: RunType
    first: bool = False
    last: bool = False

    def __str__(self):
        return f'first/last: {self.first}/{self.last}, start_time: {self.start_time}, runtype: {self.runtype.name}'

class RunCalendar:

    def __init__(self, file_path, params):
        self.file_path = file_path
        self.params = params
        self.identity = self.params['identity']
        # run_entries contains parsed rows (CalendarEntry) from calendar file (.txt)
        self.run_entries = []
        self.parse_file()

    def parse_entry(self, line):
        items = [int(i) for i in line.split()]
        if len(items) == 13:
            return CalendarEntry( 
                has_fd_run = int(items[0]) > 0, 
                start_date = datetime(*items[1:7]),
                end_date = datetime(*items[7:])
            )
        return None

    def parse_file(self):
        with open(self.file_path, "r") as f:
            for line in f:
                entry = self.parse_entry(line)
                if entry is None:
                    continue
                self.run_entries.append(entry)
   
    def get_next_entries(self, dayoffset=0, num=None):
        for i, entry in enumerate(self.run_entries):
            if entry.start_date >= datetime.now() - timedelta(days=dayoffset):
                if num is None:
                    return self.run_entries[i:]
                return self.run_entries[i:i+num]

    def get_timetable_for_entry(self, entry):
        ttable = []
        sorted_ttable=[]
        if entry.has_fd_run:
            if('raman' in [s.lower() for s in self.params[self.identity]['run_list']]):
                ttable.append(RunEntry(entry.start_date - timedelta(minutes=30), runtype=RunType.RAMAN, first=True))
                ttable.append(RunEntry(datetime(
                    year=entry.end_date.year, 
                    month=entry.end_date.month,
                    day=entry.end_date.day,
                    hour=4,
                    minute=30), runtype=RunType.RAMAN)
                )
                ttable.append(RunEntry(entry.end_date + timedelta(minutes=30), runtype=RunType.RAMAN))
            

            if('calib' in [s.lower() for s in self.params[self.identity]['run_list']]):
                ttable.append(RunEntry(entry.end_date + timedelta(minutes=60), runtype=RunType.CALIB, last=True))

            start_date = entry.start_date
            while start_date.minute != 0:
                start_date += timedelta(minutes=1)
            start_time = start_date
            while start_time <= entry.end_date:
                if start_date.minute == 0:
                    if('tank' in [s.lower() for s in self.params[self.identity]['run_list']]):
                        ttable.append(RunEntry(start_time, runtype=RunType.TANK))
                start_time += timedelta(hours=1)

            start_date = entry.start_date
            # find first valid time 
            while start_date.minute not in self.params[self.identity]['start_minutes']:
                start_date += timedelta(minutes=1)

            start_time = start_date
            while start_time <= entry.end_date:
                if start_time.strftime("%H:%M") == "04:35" or start_time.strftime("%H:%M") == "04:50":
                    start_time += timedelta(minutes=15)
                    continue
                if('fd' in [s.lower() for s in self.params[self.identity]['run_list']]):
                    ttable.append(RunEntry(start_time, runtype=RunType.FD))
                start_time += timedelta(minutes=15)

            sorted_ttable = sorted(ttable, key=lambda x: x.start_time)

            sorted_ttable[0].first = True
            sorted_ttable[-1].last = True

        return sorted_ttable
            
