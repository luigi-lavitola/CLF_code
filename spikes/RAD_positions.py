import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.Configuration import Configuration
from lib.DeviceCollection import DeviceCollection

def collect_motor():

    cfg = Configuration()
    cfg.read()

    dc = DeviceCollection()

    for mname, mparams in cfg.motors.items():
        port_params = cfg.get_port_params(mparams['port'])
        dc.add_motor(mparams['id'], mname,
            port=port_params['port'],
            speed=port_params['speed'],
            bytesize=port_params['bytesize'],
            parity=port_params['parity'],
            stopbits=port_params['stopbits'],
            timeout=port_params['timeout']
        )
    
    return dc 

def initialize_up():

    print("UPPER MOTORS INITIALIZATION:STARTING")

    dc.get_motor("UpNorthSouth").set_model(1)
    dc.get_motor("UpNorthSouth").set_acc(2000)

    dc.get_motor("UpEastWest").set_model(1)
    dc.get_motor("UpEastWest").set_acc(2000)

    print("UPPER MOTORS INITIALIZATION:COMPLETE")

def initialize_lw():
    
    print("LOWER MOTORS INITIALIZATION:STARTING")

    dc.get_motor("LwNorthSouth").set_model(1)
    dc.get_motor("LwNorthSouth").set_acc(2000)

    dc.get_motor("LwPolarizer").set_model(1)
    dc.get_motor("LwPolarizer").set_acc(2000)

def initialize_cover():
    dc.get_motor("Cover").set_model(1)
    dc.get_motor("Cover").set_acc(200)
    #dc.get_motor("Cover").compensation_B0()

def open_steering():
    dc.get_motor("Cover").move_BWD(25000)

def close_steering():
    dc.get_motor("Cover").move_FWD(25500)
  

def position_rad2():

    print("MOVING RADIOMETER 2 IN POSITION:STARTING")

    dc.get_motor("UpNorthSouth").move_ABS(1300)
    dc.get_motor("UpEastWest").move_ABS(20200)

    print("MOVING RADIOMETER 2 IN POSITION:COMPLETE")

def home_rad2():

    print("MOVING RADIOMETER 2 IN HOME:STARTING")


    dc.get_motor("UpNorthSouth").move_ABS0()
    dc.get_motor("UpEastWest").move_ABS0()

    print("MOVING RADIOMETER 2 IN HOME:COMPLETE")


def position_rad3():

    print("MOVING RADIOMETER 3 IN POSITION:STARTING")

    dc.get_motor("UpNorthSouth").move_ABS(33250)
    dc.get_motor("UpEastWest").move_ABS(4470)

    print("MOVING RADIOMETER 3 IN POSITION:COMPLETE")

def home_rad3():

    print("MOVING RADIOMETER 3 IN HOME:STARTING")

    dc.get_motor("UpNorthSouth").move_ABS0()
    dc.get_motor("UpEastWest").move_ABS0()

    print("MOVING RADIOMETER 3 IN HOME:COMPLETE")


def position_pol():

    print("MOVING POLARIZER IN POSITION:STARTING")

    dc.get_motor("LwNorthSouth").move_ABS(18900)

    print("MOVING POLARIZER IN POSITION:COMPLETE")

def home_pol():

    print("MOVING POLARIZER IN HOME:STARTING")

    dc.get_motor("LwNorthSouth").move_ABS0()

    print("MOVING POLARIZER IN HOME:COMPLETE")


def rotate_pol(degree):

    degree = float(degree)
    steps = degree*80

    print(f"ROTATING POLARIZER IN ANGLE {degree}°:STARTING")

    dc.get_motor("LwPolarizer").move_ABS(steps)

    print(f"ROTATING POLARIZER IN ANGLE {degree}°:COMPLETE")


def zero_pol():

    print("ZEROING POLARIZER:STARTING")

    dc.get_motor("LwPolarizer").move_ABS0()

    print("ZEROING POLARIZER:COMPLETE")



if __name__ == "__main__":

    dc = collect_motor()

    #initialize_up()
    #initialize_lw()

    #time.sleep(1)

    #position_rad2()
    #time.sleep(5)
    #home_rad2()
    #time.sleep(5)

    #position_rad3()
    #time.sleep(5)
    #position_pol()
    #time.sleep(5)

    #rotate_pol(90)
    #time.sleep(5)
    #rotate_pol(60)
    #time.sleep(2)

    zero_pol()
    #time.sleep(5)
    home_pol()
    #time.sleep(5)
    home_rad3()
    #time.sleep(5)
    #position_rad2()
    #initialize_cover()
    #open_steering()
    #time.sleep(5)
    #close_steering()
    


    








