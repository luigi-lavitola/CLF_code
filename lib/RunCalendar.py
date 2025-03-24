from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class CalendarEntry:
    start_date: datetime
    end_date: datetime
    raman_run: bool

    def __str__(self):
        return f'raman_run: {self.raman_run},start_date: {self.start_date}, end_date: {self.end_date}'

@dataclass
class RunEntry:
    start_time: datetime
    runtype: str        # 'raman' or 'fd'

    def __str__(self):
        return f'start_time: {self.start_time}, runtype: {self.runtype}'

class RunCalendar:

    def __init__(self, file_path):
        self.file_path = file_path
        self.run_entries = []
        self.parse_file()

    def parse_entry(self, line):
        items = [int(i) for i in line.split()]
        if len(items) == 13:
            return CalendarEntry( 
                raman_run = int(items[0]) > 0, 
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
   
    def get_next_entries(self, num=None):
        for i, entry in enumerate(self.run_entries):
            if entry.start_date >= datetime.now():
                if num is None:
                    return self.run_entries[i:]
                return self.run_entries[i:i+num]

    def get_timetable_for_entry(self, entry):
        ttable = []
        if entry.raman_run is True:
            ttable.append(RunEntry(entry.start_date - timedelta(minutes=30), runtype="raman"))
            ttable.append(RunEntry(entry.end_date + timedelta(minutes=30), runtype="raman"))

        # find first valid time 
        while entry.start_date.minute not in [15, 30, 45]:
            entry.start_date += timedelta(minutes=1)

        start_time = entry.start_date
        while start_time <= entry.end_date:
            if entry.raman_run is True and start_time.strftime("%H:%M") == "04:30":
                start_time += timedelta(minutes=15)
                continue
            ttable.append(RunEntry(start_time, runtype="fd"))
            start_time += timedelta(minutes=15)

        return ttable
            
