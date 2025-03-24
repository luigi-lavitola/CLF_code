import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import time

from lib.RunScheduler import RunScheduler



file_path = "docs/ALLFDCalendar.txt"  # Percorso del file calendario
scheduler = RunScheduler(file_path)

# Ottenere i run per la data odierna
run_info_today = scheduler.get_run_info()
print("Run per oggi:", run_info_today)

# Ottenere i run per una data specifica
data_input = input("Inserisci la data da analizzare (YYYY MM DD): ")
run_info_specific = scheduler.get_run_info(data_input)
print(f"Run per {data_input}:", run_info_specific)
