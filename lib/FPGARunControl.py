import serial
import time

class FPGARunControl:

   def __init__(self, port, baudrate = 115200):
      self.port = port
      self.baudrate = baudrate
      self.serial = None

   def connect(self):
      try:
         self.serial = serial.Serial(self.port, self.baudrate, timeout = 2)
         return 0 
      except serial.SerialException as e:
         return -2

   def close(self):
      self.serial.close()

   def read_register(self, addr):
      self.serial.write(f"{str(hex(addr))[2:]}\r".encode())
      return int(self.serial.read_until('\r'.encode()).decode()[:-1], 16)
         
   def write_register(self, addr, value):
      self.serial.write(f"{str(hex(addr))[2:]} {str(hex(value))[2:]}\r".encode())
      time.sleep(0.1)
      self.serial.read_all()

   

