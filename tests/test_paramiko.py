
import paramiko

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
