import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection

    
if __name__ == "__main__":

    print("UPPER MOTORS INITIALIZATION:STARTING")

    cfg = Configuration()
    cfg.read()

    dc = DeviceCollection()
    dc.init(cfg)

    print("UPPER MOTORS INITIALIZATION:COMPLETE")

    # procedura HOME
    # I4M-0,R
    # C
    # IA4M-0,R
    # C

    # move to position 20200
    # IA4M20200,R
    # C

    # move to position 0
    # IA4M0,R
    # C

    time.sleep(1)

    # motor
    dc.get_motor("UpEastWest").init()  
    dc.get_motor("UpEastWest").move_Neg0()  
    dc.get_motor("UpEastWest").move_Neg0()  

    dc.get_motor("UpEastWest").set_ABSzero()
    # dc.get_motor("UpEastWest").move_ABS(4470) # CLF
    dc.get_motor("UpEastWest").move_ABS(8500) # XLF

    # motor
    dc.get_motor("UpNorthSouth").init()  
    dc.get_motor("UpNorthSouth").move_Neg0()  
    dc.get_motor("UpNorthSouth").move_Neg0()  

    dc.get_motor("UpNorthSouth").set_ABSzero()
    # dc.get_motor("UpNorthSouth").move_ABS(33250)  # CLF
    dc.get_motor("UpNorthSouth").move_ABS(34250)  # XLF

    # motor
    dc.get_motor("LwNorthSouth").init()  
    dc.get_motor("LwNorthSouth").move_Neg0()  
    dc.get_motor("LwNorthSouth").move_Neg0()  

    dc.get_motor("LwNorthSouth").set_ABSzero()
    # dc.get_motor("LwNorthSouth").move_ABS(18900)  # CLF
    dc.get_motor("LwNorthSouth").move_ABS(18900)  # XLF

    # motor
    dc.get_motor("LwPolarizer").init()  
    dc.get_motor("LwPolarizer").move_Neg0()  
    dc.get_motor("LwPolarizer").move_Neg0()  

    dc.get_motor("LwPolarizer").set_ABSzero()
    dc.get_motor("LwPolarizer").move_ABS(90 * 80)

    # motor
    # command to open (Neg0 = open)
    # S1M200,R
    # C
    #dc.get_motor("Cover").set_speed(200)
    #dc.get_motor("Cover").move_Neg0()
    #dc.get_motor("Cover").move_Neg0()

    # command to close (Pos0 = close)
    #dc.get_motor("Cover").move_Pos0()

    # motor

    # 0 degrees  = SOUTH
    # 90 degrees = EAST
    # 119.7 degrees = target

    # I1M-0,R
    # C
    #dc.get_motor("Azimuth").set_speed(1500)
    #dc.get_motor("Azimuth").move_Neg0()
    #dc.get_motor("Azimuth").move_Neg0()

    # IA1M-0,R
    # C
    #dc.get_motor("Azimuth").set_ABSzero()

    # IA1M14400,R
    # C
    #dc.get_motor("Azimuth").move_ABS(90 * 80)

    # motor
    # 0 = 75 degrees
    # 90 * 80 = 335 degrees
    # 106 * 80 = 0 degrees
    # 108 * 80 = 2 degrees
    #dc.get_motor("Zenith").move_Neg0()
    #dc.get_motor("Zenith").move_Neg0()

    #dc.get_motor("Zenith").set_ABSzero()
    #dc.get_motor("Zenith").move_ABS(90 * 80)
