
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import threading
from lib.HouseKeeping import HouseKeeping

class Observer:

    def update(self, data):
        print(f'observer update: {data}')

###
    
hk = HouseKeeping()
thr = threading.Thread(target=hk.run)
thr.start()

obs = Observer()
hk.subscribe(obs.update)

while True:
    # do something else
    time.sleep(5)
    #hk.unsubscribe(obs.update)
    print("zzz...")
