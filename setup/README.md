# Installazione sul PC di controllo (Rock 5B)

Istruzioni per far girare il software CLF/XLF come servizio, con l'orologio del PC disciplinato dal GPS.
Il codice si trova in **`/opt/CLF_code`**; i comandi sono da eseguire come root (o con `sudo`).

File di questa cartella:

| File | Destinazione |
|---|---|
| `clf.service` | `/etc/systemd/system/clf.service` |
| `gpsd.default` | `/etc/default/gpsd` |
| `90-pps.rules` | `/etc/udev/rules.d/90-pps.rules` |
| `chrony-clf.conf` | `/etc/chrony/conf.d/clf.conf` (oppure in coda a `/etc/chrony/chrony.conf`) |

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

### 3.3 gpsd

```bash
cp setup/gpsd.default /etc/default/gpsd         # DEVICES="/dev/gps0 /dev/pps0"
systemctl restart gpsd
journalctl -u gpsd -n 30 --no-pager             # nessun errore su /dev/gps0 o /dev/pps0
gpspipe -w | grep -m3 '"class":"PPS"'           # una riga al secondo: gpsd usa il PPS
```

Se compaiono TPV/SKY ma non PPS, gpsd non ha aperto `/dev/pps0` (permessi o nome del device).
`-s 115200` in `gpsd.default` presuppone il ricevitore configurato a 115200 baud.

### 3.4 chrony

```bash
cp setup/chrony-clf.conf /etc/chrony/conf.d/clf.conf
# rete isolata: commentare le righe 'pool' / 'server' in /etc/chrony/chrony.conf
systemctl disable --now systemd-timesyncd      # un solo servizio sull'orologio
systemctl restart chrony
chronyc sources -v                              # dopo qualche minuto: '*' accanto a PPS
chronyc tracking                                # "System time" entro pochi microsecondi
```

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

Una lettura che non si riesce a interpretare finisce in `weather.log` come ERROR con la risposta grezza;
dopo 3, 12 e 288 letture fallite di fila (15 min, 1 h, 1 giorno) c'è anche un WARNING.

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
