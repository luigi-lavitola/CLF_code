import serial
import time

NSEC = 0.2

s = serial.Serial("/dev/ttyr07", 9600)

# init
s.write("\r\n".encode())
time.sleep(NSEC)
s.write("\r\n".encode())
time.sleep(NSEC)
s.read_all()
s.write("G\r\n".encode())
time.sleep(NSEC)
s.read_all()

# read
s.write("1B\r\n".encode())
time.sleep(NSEC)
s.read_all()

s.write("1D\r\n".encode())
time.sleep(NSEC)
s.read_until('\n'.encode())
out = s.read_until('\n'.encode())[:-2].decode()
out = out + " " + s.read_until('\n'.encode())[1:-2].decode()

# parse
data = []
for m in out.split():
   data.append(float(m.split('+')[1]))

s.close()

print(data)

d = {}
d["code"] = data[0]
d["year"] = data[1]
d["day"] = data[2]
d["hour"] = int(data[3]/100)
d["minute"] = int(data[3] - int(data[3]/100)*100)
d["temperature"] = data[4]
d["humidity"] = data[5]
d["curwspeed"] = data[6]
d["avgwspeed"] = data[7]
d["maxwspeed"] = data[8]
d["pressure"] = data[-1]

for k,v in d.items():
    print(f'{k}: {v}')


