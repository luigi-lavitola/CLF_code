import serial
import time
import logging
import datetime
from functools import partial
from logging.handlers import TimedRotatingFileHandler

CENTURION_COMMAND =30  
CENTURION_LINE =100    #Blank line (Centurion_set.txt) */
CENTURION_RETURN =255   #Return value or 'ok' */
CENTURION_WAIT =2.5  #Wait time in uS after sending command to read reply */
CENTURION_BAUD = 57600

QFREQ = 1             #Rate at which Q-switch is fired relative to doide rate (Default) */
BUFSIZE = 255         #input, output buffer size */

class Centurion:

    def __init__(self, port, baudrate=57600, parity=serial.PARITY_EVEN, timeout=2, string_return=255):
        self.port = port
        self.serial = None
        self.params = locals()
        self.params.pop('port')
        self.params.pop('self')
        self.params.pop('string_return')
        self.string_return = string_return

        #const
        self.pulse_wdth = -99
        self.state = 255
        self.sbyte = 255
        self.hbyte1 = 255
        self.hbyte2 = 255
        self.hbyte3 = 255
        self.hbyte4 = 255
        self.head_temp = -99
        self.dump_temp = -99
        self.plate_temp = -99 

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
             self.log(logging.INFO, f"CENT:CONN:Unable to create serial device: {e}: {e}")

        self.serial.port = port

        self.logger = logging.getLogger("device")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/device.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})

    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            self.log(logging.INFO, f"CENT:CONN:Unable to open device {self.port}: {e}")        
    
    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs)
        return wrapper        

    @check_open
    def read_response(self):
        try:
            response = str(self.serial.read(255).decode())
            self.log(logging.INFO, response)
            return response
        except serial.SerialException: 
            self.log(logging.INFO, f"CENT:READ_R:ERROR:Unable to read response")
            return -1

    @check_open
    def send_command(self, command):
        try:
            self.serial.flush()
            self.serial.write(f"{command}\r".encode())
            time.sleep(0.5)
            response = self.read_response()
            return response
        except serial.SerialException as e:
            self.log(logging.INFO, f"CENT:SEND_COMM:Unable to send {command} command: {e}")
            return -1
        
    @check_open
    def flush_buffers(self):
        try:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            time.sleep(0.1)
            return 0
        except Exception as e:
            self.log(logging.INFO, f"CENT:FLUSH_BUFFERS:Unable to flush buffers")
            return -1

    def comm_test(self):
        self.flush_buffers()
        time.sleep(0.1)
        command = "$HVERS ?\r"
        response = self.send_command(command)
        #response = self.read_response()
        self.log(logging.INFO, f"CENT:COMM_TEST:received:{response}")
        if response.startswith("$HVERS"):
            self.log(logging.INFO, "CENT:COMM_TEST:PASSED OK!")
            return 0
        else:
            self.log(logging.INFO, "CENT:COMM_TEST:Failed")
            return -2

    def set_parameter(self, parameter, value):
        parameter_set = self.send_command(f"{parameter} {value}")
        if parameter_set:
            preturn = parameter_set.split()
            if len(preturn) == 2 and preturn[0] == f"{parameter}" and preturn[1] == f'{value}':
                self.log(logging.INFO, f"CENT:PARAMETER_SET:Parameter {preturn[0]}, value set: {preturn[1]}")
                return 0
            else:
                self.log(logging.INFO, f"CENT:PARAMETER_SET:ERROR:Unable to set parameter {preturn[0]}")
                return -1

    def check_parameter(self, parameter):
        parameter_check = self.send_command(f"{parameter} ?")
        if parameter_check:
            preturn = parameter_check.split()
            if len(preturn) == 2 and preturn[0] == f"{parameter}":
                self.log(logging.INFO, f"CENT:PARAMETER_CHECK:Parameter {preturn[0]}, value checked: {preturn[1]}")
                return preturn[1]
            else:
                self.log(logging.INFO, f"CENT:PARAMETER_CHECK:ERROR:Unable to check parameter {preturn[0]}")
                return -1

    def set_mode(self, freq = 100, diode = 1, qson= 0, qswitch = 1, dtrig = 1, qstrig = 1, dpw = 100, qsdelay = 145):
        
        try:
            self.log(logging.INFO, "CENT:SET_MODE:Setting up Centurion Laser...")
            self.log(logging.INFO, "CENT:SET_MODE:Going Standby...")
            self.send_command("$STANDBY")
            
            for _ in range(3):
                #setting frequency (100 == 2Hz)
                self.set_parameter("$DFREQ", freq)
                #setting diodes (off = 0, enabled = 1) 
                self.set_parameter("$DIODE", diode)
                #setting Q-switch (off = 0, enabled = 1)
                self.set_parameter("$QSON", qson)
                #setting laser to be Q-switched (long pulse = 0, Q-switched = 1)
                self.set_parameter("$QSWIT", qswitch)
                #setting diode trigger in external mode (internal = 0, external = 1)
                self.set_parameter("$DTRIG", dtrig)
                #setting Q-swicth trigger to external mode (internal = 0, external = 1)
                self.set_parameter("$QSTRI", qstrig)
                #setting diodes pulse (energy of the laser)
                self.set_parameter("$DPW", dpw)
                #setting delay for Q-switch (relevant only for internal trigger)
                self.set_parameter("$QSDEL", qsdelay)
                if self.status() == 0x7E:
                    self.log(logging.INFO, "set up complete")
                    return 0
        except Exception as e:
            self.log(logging.INFO, f"CENT:SET_MODE:ERROR:Some problem occurred:{e}")
            return -1 
        
    def check_mode(self):
        self.flush_buffers()
        try:
            self.log(logging.INFO, "CENT:CHECK_MODE:Checking values:")
            self.check_parameter("$DFREQ")
            self.check_parameter("$DIODE")
            self.check_parameter("$QSON")
            self.check_parameter("$QSWIT")
            self.check_parameter("$DTRIG")
            self.check_parameter("$QSTRI")
            self.check_parameter("$DPW")
            self.check_parameter("$QSDEL")
            return 0
        except Exception as e:
            self.log(logging.INFO, "CENT:CHECK_MODE:ERROR:Some problem occurred")
            return -2

    def read_status(self):
        self.flush_buffers()
        status = self.send_command("$STATUS ?")
        if status:
            parts = status.split()
            if len(parts) == 6 and parts[0] == '$STATUS':
                try:
                    self.state = int(parts[1], 16) 
                except ValueError:
                    self.log(logging.INFO, f"CENT:READ_STATUS:ERROR:Bytes received: {status}")
                    return -1
            else:
                self.log(logging.INFO, f"CENT:READ_STATUS:ERROR:WRONG STRING RECEIVED:Bytes received: {status}")  
                return -2  

    def status(self):
        self.flush_buffers()
        status = self.send_command("$STATUS ?")
        if status:
            parts = status.split()
            if len(parts) == 6 and parts[0] == '$STATUS':
                return int(parts[1], 16)

    def read_bytes(self):
        self.flush_buffers()
        status = self.send_command("$STATUS ?")
        if status:
            parts = status.split()
            if len(parts) == 6 and parts[0] == '$STATUS':
                try:
                    self.sbyte = int(parts[2], 16) 
                    self.hbyte1 =  int(parts[3], 16) 
                    self.hbyte2 = int(parts[4], 16) 
                    self.hbyte3 = int(parts[5], 16)
                    self.log(logging.INFO, f"CENT:READ_BYTES:{self.sbyte}, {self.hbyte1}, {self.hbyte2}, {self.hbyte3}")
                except ValueError:
                    self.log(logging.INFO, f"CENT:READ_BYTES:ERROR:Bytes received: {status}")
                    return -1
            else:
                self.log(logging.INFO, f"CENT:READ_BYTES:ERROR:WRONG STRING RECEIVED:Bytes received: {status}")  
                return -2  

        self.log(logging.INFO, "CENT:READ_BYTES:Requesting shot counter")
        response = self.send_command("$SHOT ?")
        if response:
            self.log(logging.INFO, f"CENT:READ_BYTES:Shots counter:{response}")
        
        self.log(logging.INFO, "CENT:READ_BYTES:Requesting User shots counter")
        response = self.send_command("$USHOT ?")
        if response:
            self.log(logging.INFO, f"CENT:READ_BYTES:User shots counter:{response}")

        return 0     

    def standby(self):
        self.flush_buffers()
        try:
            self.log(logging.INFO, "CENT:STANDBY:Going Standby...")
            standby = self.send_command('$STAND')
            if standby:
                self.log(logging.INFO, f"CENT:STANDBY:Standby:{standby}")
        except Exception as e:
            self.log(logging.INFO, f"CENT:STANDBY:ERROR:Some problem occurred: {e}")
            return -1
          
    def warmup(self):
        self.flush_buffers()
        try:
            self.log(logging.INFO, "CENT:WARMUP:Going Standby...")
            standby = self.send_command('$STAND')
            if standby: 
                self.log(logging.INFO, f"CENT:WARMUP:Standby:{standby}")

            self.log(logging.INFO, "CENT:WARMUP:Turning On Diodes...")
            diode_on = self.send_command('$DIODE 1')
            if diode_on:
                self.log(logging.INFO, f"CENT:WARMUP:Diodes:{diode_on}")
            
            self.log(logging.INFO, "CENT:WARMUP:Q-Switch enabling")
            q_switch = self.send_command("$QSON 1")
            if q_switch:
                self.log(logging.INFO, f"CENT:WARMUP:Q-Swithc:{q_switch}")

            self.read_bytes()
            return 0 
        except Exception as e:
            self.log(logging.INFO, f"CENT:WARMUP:ERROR:Some problem occurred: {e}")
            return -1

    def sleep(self):
        self.flush_buffers()
        try:
            self.log(logging.INFO, "CENT:SLEEP:Sending Centurion to sleep")

            sleep = self.send_command("$STOP ?")
            if sleep:
                self.log(logging.INFO, f"CENT:SLEEP:Centurion sent to sleep: {sleep}")
                self.log(logging.INFO, 'ZZZZ...ZZZZ...ZZZZ...')
            return 0
        except Exception as e:
            self.log(logging.INFO, f"CENT:SLEEP:ERROR:Centurion doesn't want to sleep")
            return -1
            
    def check_temps(self):
        self.flush_buffers()
        temps = self.send_command("$TEMPS ?")
        if temps: 
            parts = temps.split()
            if len(parts) == 4 and parts[0] == '$TEMPS':
                    
                try:
                    self.head_temp = int(parts[1])
                    self.dump_temp = int(parts[2])
                    self.plate_temp = int(parts[3])

                    self.log(logging.INFO, f"CENT:CHECK_TEMPS:TEMPS:head:{self.head_temp}, dump:{self.dump_temp}, plate:{self.plate_temp}")
                    return 0

                except ValueError:
                    self.log(logging.INFO, f"CENT:CHECK_TEMPS:ERROR:BYTE RECEIVED {temps}")
                    return -1
            else:
                self.log(logging.INFO, f"CENT:CHECK_TEMPS:ERROR:Bytes received: {temps}")  
                return -2        

    def temperature(self):
        self.flush_buffers()
        temps = self.send_command("$TEMPS ?")
        if temps:
            parts = temps.split()
            if len(parts) == 4 and parts[0] == '$TEMPS':
                return int(parts[1]), int(parts[2]), int(parts[3])

    def fire_auth(self):
        return self.status() == 0x7E
        
    def check_qs_delay(self):
        self.flush_buffers()
        self.check_parameter("$QSDELAY")
   
    def check_pwdth(self):
        self.pulse_wdth = -99
        self.flush_buffers()

        try: 
            pwdth= self.send_command("$DPW ?")
            if pwdth:
                parts = pwdth.split()
                if parts == 2 and parts[0]== 'DPW':
                    try:
                        self.pulse_wdth = parts[1]
                        self.log(logging.INFO, f"CENT:CHECK_PULSE_WIDTH:Pulse width: {self.pulse_wdth}")
                        return(self.pulse_wdth)
                    except ValueError:
                        self.log(logging.INFO, f"CENT:CHECK_PULSE_WIDTH:ERROR:Bytes received: {parts}")
                        return -1
        except Exception as e:
            self.log(logging.INFO, f"CENT:CHECK_PULSE_WIDTH:ERROR:Some problem occurred: {e}")

    def set_pwdth(self, pwd):
        self.flush_buffers()
        self.set_parameter("$DPW", pwd)

    def fire(self):
        self.flush_buffers()
        status = self.read_status()

        #while self.state != "7e":
        #    self.send_command("$STAND")
        #    status = self.read_status()

        self.check_temps()
        if self.head_temp <= 500 and self.dump_temp <= 450 and self.plate_temp <= 450:
            self.send_command("$FIRE")
           

if __name__ == "__main__":
    c = Centurion("/dev/ttyr01", 57600, 2, serial.PARITY_EVEN, 255)

    # usage with serial object as parameter
    #s = serial.Serial("/dev/ttyUSB0", 57600)
    #c = Centurion(s)

    c.check_temps()
    c.warmup()
    c.fire()
#        self.flush_buffers()
#        try:
#            pulse_width = self.send_command(f"$DPW {pwd}")
#            if pulse_width:
#                self.log(logging.INFO, f"CENT:SET_PULSE_WIDTH:Pulse width set: {pulse_width}")
#
#                self.check_pwdth()
#        except Exception as e:
#            self.log(logging.INFO, f"CENT:SET_PULSE_WIDTH:ERROR:Some problem occurred: {e}")
#            return -1
#
#    def set_mode_old(self):
#        
#        try: 
#
#            self.flush_buffers()
#            self.conf_file = '' #CERCARE FILE
#            with open(self.conf_file, "r") as read_conf:
#                self.log(logging.INFO, f"CENT:SET_MODE:file {read_conf} open")
#
#                for line in read_conf:
#                    line=line.strip()
#
#                    if line.startswith("$"):
#                        parts = line.split()
#                    if len(parts) <2:
#                        continue
#                    
#                    self.log(logging.INFO, f"CENT:SET_MODE:command {line}")
#                    command = self.send_command(line)
#                    if command:
#                        self.log(logging.INFO, f"CENT:SET_MODE:command {command} received")
#
#                    inquiry = read_conf.readline().strip()
#                    self.log(logging.INFO, f"CENT:SET_MODE:command {inquiry}")
#                    response = self.send_command(inquiry)
#                    if response:
#                        self.log(logging.INFO, f"CENT:SET_MODE:command {inquiry} received")
#
#                    comment = read_conf.readline().strip()
#                    self.log(logging.INFO, f"CENT:SET_MODE:{comment}")          
#            
#            self.flush_buffers()
#            seriall = self.send_command('$SERIA ?')
#            if seriall:
#                self.log(logging.INFO, f"CENT:SET_MODE:SERIAL NUMBER:{seriall}")
#
#            self.flush_buffers()
#            shot_count = self.send_command('$SHOT ?')
#            if shot_count: 
#                self.log(logging.INFO, f"CENT:SET_MODE:SHOT COUNT:{shot_count}")
#
#            self.flush_buffers()
#            user_shot = self.send_command('$USHOT ?')
#            if user_shot:
#                self.log(logging.INFO, f"CENT:SET_MODE:USER CONTROLLED SHOT COUNTER:{user_shot}")
#
#            self.flush_buffers()
#            h_vers= self.send_command('$HVERS ?')
#            if h_vers:
#                self.log(logging.INFO, f"CENT:SET_MODE:HARDWARE VERSION:{h_vers}")
#
#            self.flush_buffers()
#            temps = self.send_command('$TEMPS ?')
#            if temps:
#                self.log(logging.INFO, f"CENT:SET_MODE:TEMPERATURES:{temps}")
#
#        except FileNotFoundError:
#            self.log(logging.INFO, f"CENT:SET_MODE:ERROR:file {self.conf_file} not found")
#
#        except serial.SerialException as e:
#            self.log(logging.INFO, f"CENT:SET_MODE:serial error: {e}")
#
#    def check_qs_delay_old(self):
#
#            self.flush_buffers()
#
#            self.qsdelay = -99
#
#            try:
#                delay = self.send_command("$QSDELAY ?")
#                if delay:
#                    parts = delay.split()
#                    if parts == 2 and parts[0]== "QSDELAY":
#                        try:
#                            parts[1] = self.qsdelay
#                            self.log(logging.INFO, f"CENT:CHECHK_QSWITCH_DELAY:{self.qsdelay}")
#                            return(self.qsdelay)
#
#                        except ValueError:
#                            
#                            self.log(logging.INFO, f"CENT:CHECK_QSWITCH_DELAY:ERROR:Bytes received: {delay}")
#                            return -1
#
#            except Exception as e:
#                self.log(logging.INFO, f"CENT_QSWITCH_DELAY:ERROR:Some problem occurred:{e}")
#                return 0 
