#!/usr/bin/env python3

import time
import gps


def safe_get(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def main():
    print("Connessione a gpsd...")

    gpsd = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)

    print("Lettura dati GPS. Premi CTRL+C per uscire.\n")

    while True:
        try:
            report = gpsd.next()
            time.sleep(1)
            if report["class"] == "TPV":
                mode = safe_get(gpsd.fix, "mode", 0)

                print("=" * 50)
                print(f"UTC gpsd        : {safe_get(gpsd, 'utc')}")
                print(f"UTC fix         : {safe_get(gpsd.fix, 'time')}")
                print(f"Fix mode        : {mode}")

                if mode == 1:
                    print("Fix status      : NO FIX")
                elif mode == 2:
                    print("Fix status      : 2D FIX")
                elif mode == 3:
                    print("Fix status      : 3D FIX")
                else:
                    print("Fix status      : UNKNOWN")

                print(f"Latitude        : {safe_get(gpsd.fix, 'latitude')}")
                print(f"Longitude       : {safe_get(gpsd.fix, 'longitude')}")
                print(f"Altitude        : {safe_get(gpsd.fix, 'altitude')}")
                print(f"Speed m/s       : {safe_get(gpsd.fix, 'speed')}")
                print(f"Track deg       : {safe_get(gpsd.fix, 'track')}")
                print(f"Climb m/s       : {safe_get(gpsd.fix, 'climb')}")

                print(f"Time error eps  : {safe_get(gpsd.fix, 'eps')}")
                print(f"Lon error epx   : {safe_get(gpsd.fix, 'epx')}")
                print(f"Lat error epy   : {safe_get(gpsd.fix, 'epy')}")
                print(f"Alt error epv   : {safe_get(gpsd.fix, 'epv')}")
                print(f"Speed error eps : {safe_get(gpsd.fix, 'eps')}")

            elif report["class"] == "SKY":
                satellites = safe_get(gpsd, "satellites", [])

                print("-" * 50)
                print(f"Satelliti visibili: {len(satellites)}")

                used = 0
                for sat in satellites:
                    if safe_get(sat, "used", False):
                        used += 1

                print(f"Satelliti usati   : {used}")

        except KeyboardInterrupt:
            print("\nUscita.")
            break

        except StopIteration:
            print("gpsd ha terminato lo stream.")
            break

        except Exception as e:
            print(f"Errore GPS: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
