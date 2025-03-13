import sys
import os
import csv
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.TLA2518 import TLA2518
from pyftdi.spi import SpiController

# Configura il controller SPI
spi = SpiController()
spi.configure('ftdi://ftdi:4232h/2')
slave = spi.get_port(cs=0, freq=30E6, mode=0)

# Inizializza l'ADC
tla = TLA2518()
adc = tla.get_ftdi_backend(slave)

# Nome del file di log
log_file = "adc_log_calib.csv"
calib=[12.698329443235162, 12.857486052905534, 12.580072988236255, 12, 12, 12, 12, 12.597657636342127]

# Scrive l'intestazione del file CSV se non esiste
def initialize_csv():
    if not os.path.exists(log_file):
        with open(log_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp"] + [f'AIN{ch}' for ch in range(8)])

# Funzione per registrare i dati su file
def log_data():
    while True:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [adc.read_channel(ch)*calib[ch] for ch in range(8)]
        
        with open(log_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp] + values)
        
        time.sleep(60)  # Aspetta un minuto prima di registrare di nuovo

# Inizializza il file CSV
initialize_csv()

# Avvia la registrazione
display_message = "Logging ADC data every minute. Press Ctrl+C to stop."
print(display_message)
try:
    log_data()
except KeyboardInterrupt:
    print("\nLogging stopped.")

