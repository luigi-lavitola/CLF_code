# Installazione sul PC di controllo (Rock 5B)

Istruzioni per far girare il software CLF/XLF come servizio, con l'orologio del PC disciplinato dal GPS.
Il codice si trova in **`/opt/CLF_code`**; i comandi sono da eseguire come root (o con `sudo`).

File di questa cartella:

| File | Destinazione |
|---|---|
| `clf.service` | `/etc/systemd/system/clf.service` |
| `gpsd.default` | `/etc/default/gpsd` |
| `90-pps.rules` | `/etc/udev/rules.d/90-pps.rules` |
| `clf-night-report.service`, `.timer` | `/etc/systemd/system/` (§4d) |
| `chrony-clf.conf` | `/etc/chrony/conf.d/clf.conf` (oppure in coda a `/etc/chrony/chrony.conf`) |
| `99-clf-serial.rules` | `/etc/udev/rules.d/99-clf-serial.rules` |
| `pps-gpio.dts` | overlay del PPS (vedi §0.2) |

Su un Rock **nuovo** partire dal §0; su un PC già installato basta dal §1.

---

## 0. Rock 5B nuovo

Provato il 2026-11-11 su **Armbian 26.11 (Debian 13 trixie), kernel 6.18 `current-rockchip64`**.
I PC in sito hanno invece l'immagine Radxa (Debian 12, kernel 6.1 Rockchip): le differenze sono indicate.

```bash
timedatectl set-timezone UTC
hostnamectl set-hostname clf-rock-5b             # o xlf-rock-5b
apt update && apt full-upgrade
```

Se `apt` reinstalla il pacchetto del kernel, `uname -r` e `/lib/modules/` possono non coincidere
fino al reboot (nessun modulo caricabile, nemmeno `pps-gpio`): riavviare prima di provare il PPS.

### 0.1 Porte USB

| Device | Chip | Uso |
|---|---|---|
| `/dev/runcontrol` | CMOD A7 (Digilent 0403:6010), interfaccia 1 | registri FPGA |
| `/dev/fpgaprog` | CMOD A7, interfaccia 0 | JTAG |
| `/dev/gps0` | FT4232H (0403:6011), interfaccia 2 | GPS LEA-M8F (low latency) |
| `/dev/data0` | FT4232H, interfaccia 3 | UART dati della FPGA |
| — | FT4232H, interfacce 0 e 1 | SPI dell'housekeeping (pyftdi) |

```bash
apt install setserial
cp setup/99-clf-serial.rules setup/90-pps.rules /etc/udev/rules.d/
udevadm control --reload && udevadm trigger --subsystem-match=tty --action=add
ls -l /dev/runcontrol /dev/fpgaprog /dev/gps0 /dev/data0
```

Le regole non usano numeri di serie (il FT4232H non ne ha, e così la CMOD A7 si può sostituire):
sul PC ci deve essere un solo FT4232H e una sola scheda Digilent.

### 0.2 PPS dal GPIO

Il PPS (`PPS_out_PC` della FPGA) entra su **GPIO3_A4** (`gpios = <&gpio3 4 0>`), come sui PC in sito.

```bash
armbian-add-overlay setup/pps-gpio.dts           # Armbian: compila in /boot/overlay-user, user_overlays=pps-gpio
reboot
cat /sys/class/pps/pps0/name                     # pps@0.-1  (pps1 "usbserial..." è quello di gpsd sul DCD: non usato)
ppstest /dev/pps0                                # una riga "assert" al secondo, con la FPGA programmata
```

Immagine Radxa: `dtc -@ -I dts -O dtb -o /boot/dtbo/pps.dtbo setup/pps-gpio.dts` e
`fdtoverlays /boot/dtbo/pps.dtbo` in `/boot/extlinux/extlinux.conf`.

### 0.3 Firmware della FPGA nella flash

La CMOD A7 si programma una volta nella flash SPI e riparte da sola a ogni accensione:

```bash
apt install openfpgaloader
openFPGALoader -b cmoda7_35t --detect               # idcode 0x362d093, xc7a35
openFPGALoader -b cmoda7_35t -f --verify topm.bit   # scrive e verifica la flash (MX25L3233F)
openFPGALoader -b cmoda7_35t -r                     # riparte dalla flash, come all'accensione
python3 tools/fpga_status.py /dev/runcontrol --hw 2 # 0xFC = data del bitstream, PPS_PRESENT=1
```

openFPGALoader contiene già il bitstream ponte JTAG→SPI per xc7a35t cpg236.
Con `xc3sprog` la FPGA si vede con il cavo `jtaghs1_fast` (`xc3sprog -c jtaghs1_fast -j`), ma per la
flash servirebbe un bitstream `bscan_spi` per cpg236, che il pacchetto Debian non contiene.

### 0.4 Driver MOXA (porte `/dev/ttyr00`…`0f`)

Le porte di laser, RPC, radiometri, motori e meteo (`conf/<sito>/ports.yml`) sono su un MOXA NPort a 16
porte in modalità **Real COM**. Driver "NPort Real TTY Driver for Linux" dal sito MOXA (pagina della
serie NPort 5600): per kernel 6.x la **v6.2** (`moxa-real-tty-linux-kernel-6.x-driver-v6.2.tar`).

```bash
apt install build-essential linux-headers-current-rockchip64   # header del kernel in uso
mkdir -p /root/moxa && cd /root/moxa
tar xf moxa-real-tty-linux-kernel-6.x-driver-v6.2.tar
cd moxa && ./mxinst                              # avviso sul kernel: invio; "secure function": N
cd /usr/lib/npreal2/driver
./mxaddsvr <IP del MOXA> 16                      # crea ttyr00..ttyr0f, porte dati 950.., comandi 966..
```

`mxinst` installa e abilita `npreal2.service`. `mxaddsvr` scrive solo la configurazione
(`npreal2d.cf`): si può fare anche senza il MOXA collegato. Per cambiare IP:
`./mxdelsvr <vecchio IP>` e di nuovo `./mxaddsvr <nuovo IP> 16`.
Dopo un aggiornamento del kernel il modulo va ricompilato (di nuovo `./mxinst`).

---

## 1. Codice e configurazione

```bash
git clone <url del repo> /opt/CLF_code        # oppure: cd /opt/CLF_code && git pull
cd /opt/CLF_code
cp conf/parameters.yml.sample conf/parameters.yml
nano conf/parameters.yml                       # identity (clf/xlf), hw_version, *_trigger_ms
```

`conf/parameters.yml` non è versionato: va creato una volta su ogni PC.

## 2. Pacchetti

```bash
apt install python3 python3-pip screen gpsd gpsd-clients chrony pps-tools python3-gps
# tutte le dipendenze tranne gps (si usa python3-gps di apt, stessa versione di gpsd)
grep -v '^gps' requirements.txt > /tmp/req.txt
pip3 install -r /tmp/req.txt                   # Debian 12+: aggiungere --break-system-packages
```

Su Debian 12 e derivate `pip` rifiuta di installare nel Python di sistema senza
`--break-system-packages` (PEP 668). In alternativa si possono installare i pacchetti `python3-...`
equivalenti con apt, se le versioni vanno bene.

## 3. Ora del PC: UTC, GPS + PPS

Il software richiede che l'orologio del PC sia **in UTC e sincronizzato**:
- calendario e scheduler usano l'ora locale del PC (`datetime.now()`) e il calendario è in UTC;
- all'avvio, e prima di ogni run con timestamp, il contatore dei secondi della FPGA viene allineato all'orologio del PC.

### 3.1 Fuso orario

```bash
timedatectl set-timezone UTC
timedatectl                                     # Time zone: Etc/UTC
```

### 3.2 PPS dal GPIO

Il PPS arriva dalla FPGA (`PPS_out_PC`) su un GPIO, come `/dev/pps0`.

```bash
ppstest /dev/pps0                               # una riga "assert" al secondo
cp setup/90-pps.rules /etc/udev/rules.d/
udevadm control --reload && udevadm trigger /dev/pps0
ls -l /dev/pps0 /dev/gps0                       # pps0: root dialout crw-rw----; gps0: link alla seriale del GPS
```

### 3.3 GPS u-blox LEA-M8F (una volta sola)

Di fabbrica il modulo esce a **9600 baud**, solo NMEA. A 9600 la linea è già all'80% e i
messaggi UBX che gpsd attiva non ci starebbero; `gpsd.default` usa `-s 115200`.
Si porta la porta a 115200 e si salva in flash, con gpsd fermo:

```bash
systemctl stop gpsd
python3 tools/gps_probe.py /dev/gps0 -b 9600 -t 5 --poll   # cosa manda, baud attuale, CFG-TP5
ubxtool -f /dev/gps0 -s 9600 -S 115200                      # nuovo baud della UART1
ubxtool -f /dev/gps0 -s 115200 -p SAVE                      # salva in flash
python3 tools/gps_probe.py /dev/gps0 -b 115200 -t 5        # deve leggere i messaggi a 115200
```

Messaggi UBX periodici per l'housekeeping (`lib/GpsInfo.py`: tAcc, holdover, deriva
dell'oscillatore, AGC/jamming), ogni 10 epoche, poi di nuovo `SAVE`:

```bash
ubxtool -f /dev/gps0 -s 115200 -c 0x06,0x01,0x01,0x20,0x0a   # NAV-TIMEGPS
ubxtool -f /dev/gps0 -s 115200 -c 0x06,0x01,0x01,0x22,0x0a   # NAV-CLOCK
ubxtool -f /dev/gps0 -s 115200 -c 0x06,0x01,0x0a,0x2e,0x0a   # MON-SMGR (holdover)
ubxtool -f /dev/gps0 -s 115200 -c 0x06,0x01,0x0a,0x09,0x0a   # MON-HW
ubxtool -f /dev/gps0 -s 115200 -p SAVE
```

L'housekeeping li riceve da gpsd come hex dump (`?WATCH` con `raw:1`): con gpsd acceso,
`gpspipe -R` deve mostrare pacchetti che iniziano con `b562`, e in `hk.csv` le colonne
`gps_tacc_ns` … `gps_jam` non devono restare `nan`.

Il PPS per l'FPGA è **TIMEPULSE2** (1 s, impulso 100 ms, fronte di salita, nessun impulso
finché il modulo non è agganciato). TIMEPULSE1 non è usato come timepulse.

### 3.4 gpsd

```bash
cp setup/gpsd.default /etc/default/gpsd         # DEVICES="/dev/gps0 /dev/pps0"
systemctl restart gpsd
journalctl -u gpsd -n 30 --no-pager             # nessun errore su /dev/gps0 o /dev/pps0
gpspipe -w | grep -m3 '"class":"PPS"'           # una riga al secondo: gpsd usa il PPS
gpspipe -w | grep -m3 '"class":"TPV"'           # deve contenere "leapseconds":18
```

Se compaiono TPV/SKY ma non PPS, gpsd non ha aperto `/dev/pps0` (permessi o nome del device).
Se in TPV manca `leapseconds`, gpsd legge solo NMEA (avviato con `-b`, o baud sbagliato):
senza UBX mancano `gps_leapseconds` e `gps_tdop` in `hk.log` e il controllo della tabella dei
leap second non scatta. Con gpsd acceso il modulo si interroga attraverso gpsd:
`ubxtool -p MON-VER`, `ubxtool -p CFG-TP5`, `ubxtool -p MON-HW` (lo stato dell'antenna).

### 3.5 chrony

```bash
cp setup/chrony-clf.conf /etc/chrony/conf.d/clf.conf
# rete isolata: commentare le righe 'pool' / 'server' in /etc/chrony/chrony.conf
systemctl disable --now systemd-timesyncd      # un solo servizio sull'orologio
systemctl restart chrony
chronyc sources -v                              # dopo qualche minuto: '*' accanto a PPS
chronyc tracking                                # "System time" entro pochi microsecondi
```

**Attenzione:** se `/dev/pps0` non esiste (overlay mancante, kernel e moduli non coerenti), chrony
non parte affatto (`Fatal error : Could not open /dev/pps0`) e il PC resta senza sincronizzazione.

Se la sorgente GPS risulta sempre spostata di qualche decimo di secondo, correggere `offset` nella riga
`refclock SHM 0` di `clf.conf` con quel valore (deve solo stare entro ±0.5 s perché `lock GPS` funzioni).

## 4. Servizio

```bash
# se c'era un servizio precedente per main.py/screen, disattivarlo:
#   systemctl disable --now <vecchio servizio>
cp setup/clf.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clf
systemctl status clf
```

All'avvio il servizio aspetta fino a ~5 minuti che chrony sia sincronizzato (entro 10 ms), poi parte
comunque.

### Uso

| Cosa | Comando |
|---|---|
| collegarsi alla CLI | `screen -r clf` |
| scollegarsi lasciandola attiva | `Ctrl-A` poi `D` |
| fermare il software | `systemctl stop clf` |
| riavviarlo | `systemctl restart clf` |
| stato e ultimi messaggi del servizio | `systemctl status clf`, `journalctl -u clf` |

Note:
- `quit` dalla CLI chiude `main.py`, e il servizio lo **riavvia** dopo 10 s (`Restart=always`):
  per fermarlo davvero usare `systemctl stop clf`.
- `stop`/`restart` del servizio durante un run terminano anche il processo del run, **senza abort**:
  prima di fermare, controllare con `status` nella CLI che non ci sia un run in corso.
  Se succede, il `prepare` del run successivo o lo shutdown automatico (nessun run nei prossimi 45 min,
  oppure un allarme) riportano la stazione in stato sicuro.
- Per lavorare sugli strumenti a mano passare in `mode manual`: in auto, con l'inverter acceso e nessun
  run vicino, la stazione viene spenta automaticamente.

## 4b. Stazione meteo (solo sul PC collegato alla stazione)

`tools/weather_logger.py` legge la stazione ogni 5 minuti (allineato a :00, :05, ...) e scrive
`logs/weather_log.csv` (stesse colonne del vecchio `spikes/weather_log.py`, timestamp UTC) e
`logs/weather.log`. Porta e velocità sono quelle di `weather_Station` in `conf/<identity>/ports.yml`.

Prima prova a mano (una lettura, mostra anche la risposta grezza della stazione):
```bash
cd /opt/CLF_code
python3 tools/weather_logger.py --once
```

Poi il servizio:
```bash
# se il vecchio spikes/weather_log.py gira ancora (screen, cron, ...), fermarlo:
#   altrimenti due processi leggono la stessa porta
cp setup/clf-weather.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clf-weather
systemctl status clf-weather
tail -f logs/weather.log
```

La stazione è collegata al MOXA, che è alimentato dall'inverter: **risponde solo mentre l'inverter è
acceso** (durante i run). Quando non risponde le letture vengono saltate, con un solo messaggio INFO
quando smette e uno quando torna a rispondere. Una risposta che non si riesce a interpretare finisce invece
in `weather.log` come ERROR con la risposta grezza.
Per avere dati meteo 24 ore su 24 serve alimentare il MOXA indipendentemente dall'inverter, oppure
collegare la stazione direttamente al PC (adattatore USB-seriale, porta da aggiornare in `ports.yml`).

## 4c. Dashboard di turno

`dashboard/app.py` (Flask) mostra in una pagina web i log degli ultimi giorni: notti e run, qualità dei
timestamp, temporizzazione, energia del laser, housekeeping, eventi. È **solo lettura**: legge i file in
`logs/` e non tocca l'hardware (i comandi restano nella CLI).

```bash
apt install python3-flask
cp setup/clf-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clf-dashboard
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/     # 200
```

### Accesso da fuori

La rete è chiusa: si passa dalla macchina INFN pubblica e dal gateway dell'esperimento.
Una volta per tutte, in `~/.ssh/config` sul proprio PC:

```
Host infn-jump
    HostName <macchina INFN pubblica>
    User <utente>

Host auger-gw
    HostName 168.96.149.225
    Port 19422
    User root
    ProxyJump infn-jump
```

Poi, ogni volta (lasciare il comando aperto):
```bash
ssh -N -L 8080:<IP del PC CLF nella rete interna>:8080 auger-gw
```
e aprire **http://localhost:8080** nel browser.
(In alternativa `sshuttle -r auger-gw <subnet CLF>` e poi `http://<IP del PC CLF>:8080`.)

Uso della pagina:
- periodo: 1, 3, 7, 30 giorni o tutto, fino all'ultimo dato presente nei log;
- clic su un punto di un run: dettaglio colpo per colpo;
- link diretti: `?days=7`, `?run=<id>` (un run), `?theme=light|dark`.

La pagina carica Plotly da `cdn.plot.ly`: il browser del proprio PC deve avere accesso a internet
(il PC CLF no).

## 4d. Rapporto della notte su Telegram

`tools/night_report.py` manda ogni mattina un messaggio (in inglese) con il riassunto della notte appena
finita: run eseguiti rispetto a quelli del calendario FD, run uccisi / con errori / senza colpi / rifiutati
per allarme, timestamp validi, righe ERROR e WARNING dei log, log fermi prima della fine della notte.
Un messaggio per sito, ogni mattina anche quando va tutto bene: **se non arriva, qualcosa è fermo**.
Serve accesso a internet in uscita verso `api.telegram.org`.

Credenziali del bot in `conf/telegram.yml` (non versionato, come `parameters.yml`):
```yaml
token: "123456789:AA..."        # da BotFather
chat_id: 123456789              # utente, o gruppo (numero negativo)
```
Il chat id: scrivere un messaggio al bot (o nel gruppo in cui è stato aggiunto), poi
`curl -s https://api.telegram.org/bot<TOKEN>/getUpdates` e leggere `"chat":{"id":...}`.

```bash
chmod 600 conf/telegram.yml
python3 tools/night_report.py --dry-run                      # stampa il messaggio, non lo manda
python3 tools/night_report.py --night 2026-11-11 --dry-run   # una notte precisa
cp setup/clf-night-report.service setup/clf-night-report.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now clf-night-report.timer                # ogni giorno alle 12:05 UTC
systemctl start clf-night-report                             # prova subito: deve arrivare il messaggio
systemctl list-timers clf-night-report.timer
```

La notte D va dalle 12:00 UTC di D alle 12:00 di D+1; l'ultimo run del calendario (CALIB) può finire
verso le 11:15 UTC. Con `--only-problems` non manda niente quando è tutto a posto (sconsigliato).

## 5. Log

In `/opt/CLF_code/logs/` (ruotati ogni giorno alle 18:00 UTC):

| File | Contenuto |
|---|---|
| `run.log` | run, scheduler, allarmi, allineamento del tempo FPGA, colpi (`gps_seconds`, `counter`, ...) |
| `device.log` | dialogo con laser, motori, radiometri, RPC |
| `hk.log`, `hk.csv` | housekeeping ogni 10 s (tensioni, temperature, pioggia, GPS) |
| `screen.log` | quello che la CLI stampa sul terminale |
| `weather.log`, `weather_log.csv` | stazione meteo, ogni 5 min (solo dove gira `clf-weather`) |

## 6. Verifica dopo l'installazione

```bash
screen -r clf
```
e nella CLI:
- `status` → `mode: auto`, scheduler e prossimo run;
- `fpga_time check` → `offset from host 0 s`.

In `logs/hk.log`:
- `gps_fix=True`, `gps_sats_used` > 4, `gps_clock_offset` sotto 0.001 s (con chrony agganciato al PPS);
- nessun warning `host clock - GPS` o `leap seconds`.

In `logs/run.log` all'avvio: `FPGA seconds counter aligned ...`.
