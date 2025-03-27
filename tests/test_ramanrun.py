
import os
import sys
import time
import paramiko
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection
from lib.RunManager import RunManager, RunType

### HELPERS

def WAIT_UNTIL_TRUE(func):
    while True:
        if func():
            break

### CONFIG 

cfg = Configuration()
cfg.read()

dc = DeviceCollection()
dc.init(cfg)

### 

nshots = 75000
#nshots = 1000

###

print("configure FPGA registers for RAMAN run...")
dc.fpga.write_register('pps_delay', 0)
dc.fpga.write_bit('laser_en', 1)
dc.fpga.write_register('pulse_width', 10_000)  # 100 us
dc.fpga.write_register('pulse_energy', 17_400) # 140 us = 174 us, maximum
dc.fpga.write_register('pulse_period', 1_000_000) # 10 ms
dc.fpga.write_register('shots_num', nshots)

dc.fpga.write_register('mux_bnc_0', 0b0010)
dc.fpga.write_register('mux_bnc_1', 0b0010)
dc.fpga.write_register('mux_bnc_2', 0b0010)
dc.fpga.write_register('mux_bnc_3', 0b0010)
dc.fpga.write_register('mux_bnc_4', 0b0010)
print("done")

print("turn on inverter... ")
dc.fpga.write_dio('inverter', True)
print("done")

print("wait RPC and MOXA power up...")
for _ in range(10):
    time.sleep(1)
    print('.', end='')
    sys.stdout.flush() 
print("done")

print("turn on Radiometer outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('radiometer').on)
print("done")

print("turn on Laser outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('laser').on)
print("done")

print("turn on VXM outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('VXM').on)
print("done")

print("wait power up...")
for _ in range(10):
    time.sleep(1)
    print('.', end='')
    sys.stdout.flush() 
print("done")

print("laser setup...")
dc.laser.set_mode(qson = 1, dpw = 140)
print("done")

print("laser warmup...")
dc.laser.warmup()
print("done")

print("radiometer 3700 setup...")
dc.get_radiometer('Rad1').setup()
print("done")

##

print("select RAMAN beam...")
dc.fpga.write_dio('flipper_raman', True)
print("done")

print("turn on RAMAN DAQ...")
WAIT_UNTIL_TRUE(dc.get_outlet("RAMAN_inst").on)
print("done")

print("check rain and cover status...")
if dc.fpga.read_dio('rain') == (not dc.fpga.read_dio('norain')):
    if dc.fpga.read_dio('rain'):
        print("IT IS RAINING... ALARM!")
print("done")

if dc.fpga.read_dio('cover_raman_open') == 1 \
    and dc.fpga.read_dio('cover_raman_closed') == 1:
    print("COVER ERROR!!!")

print("open cover...")
WAIT_UNTIL_TRUE(dc.get_outlet("RAMAN_cover").on)
print("done")

print("wait cover opening...")
while dc.fpga.read_dio('cover_raman_open') == dc.fpga.read_dio('cover_raman_closed'):
    time.sleep(1)
    print('.', end='')
    sys.stdout.flush() 
print("done")

print("wait for laser fire auth...")
while not dc.laser.fire_auth():
    print(dc.laser.temperature())
    time.sleep(1)
print("set laser in fire mode...")
dc.laser.fire()
print("done")

print("start RAMAN run...")
dc.fpga.write_dio('laser_en', 1)
dc.fpga.write_dio('laser_start', 1)

hostname = "192.168.218.191"
username = "root"
password = "ariag25"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname, username=username, password=password)

# start command and get process PID
stdin, stdout, stderr = client.exec_command("./start12 >& /media/data/rdata/start12.log & echo $!")
pid = stdout.read().decode().strip()
print(f"PID: {pid}")
print("done")

print("wait for laser shots end...")
while True:
    ns = dc.fpga.read_register('shots_cnt')
    if ns == nshots:
        break
    print(f'shots: {ns}, rain: {dc.fpga.read_dio("rain")}')
    time.sleep(1) 
    # check rain sensor
print("done")

print("waiting for RAMAN DAQ process to finish...")
while True:
    stdin, stdout, stderr = client.exec_command(f"ps -p {pid} -o comm=")
    process_name = stdout.read().decode().strip()

    if not process_name:
        break
    else:
        time.sleep(1)
        print('.', end='')
        sys.stdout.flush() 
print("done")

## 

print("unselect RAMAN beam...")
dc.fpga.write_dio('flipper_raman', False)
print("done")

print("laser standby...")
dc.laser.standby()
print("done")

print("close cover...")
WAIT_UNTIL_TRUE(dc.get_outlet("RAMAN_cover").off)
print("done")

print("wait cover closing...")
while dc.fpga.read_dio('cover_raman_open') == dc.fpga.read_dio('cover_raman_closed'):
    time.sleep(1)
    print('.', end='')
    sys.stdout.flush() 
print("done")

print("turn off Radiometer outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('radiometer').off)
print("done")

print("turn off Laser outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('laser').off)
print("done")

print("turn off VXM outlet... ")
WAIT_UNTIL_TRUE(dc.get_outlet('VXM').off)
print("done")

print("turn off inverter... ")
dc.fpga.write_dio('inverter', False)
print("done")
