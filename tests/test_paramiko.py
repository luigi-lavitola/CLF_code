
import paramiko

hostname = "192.168.218.191"
username = "root"
password = "xxxx"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname, username=username, password=password, look_for_keys=False, allow_agent=False)

# start command and get process PID
#stdin, stdout, stderr = client.exec_command("./start12 >& /media/data/rdata/start12.log & echo $!")
stdin, stdout, stderr = client.exec_command("echo $HOME")
#pid = stdout.read().decode().strip()
#print(f"PID: {pid}")
