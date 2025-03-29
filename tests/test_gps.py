
import gps
import time

gpsd = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)

while True:
    gpsd.next()
    print(f"satellites used: {gpsd.satellites_used}")
    print(f"fix: {gpsd.fix.mode}")
    time.sleep(0.2)

