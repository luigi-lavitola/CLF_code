#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from lib.Radiometer import Radiometer3700, RadiometerOphir

rm1 = Radiometer3700("/dev/ttyr02")
rm1.info()
rm1.set("TG", 3)
rm1.set("foo", 3)                       # UNK
print(f'TG = {rm1.get("TG")}')
print(f'MUU = {rm1.get("MUU")}')        # UNK
rm1.setup()
print("\n\n")

rm2 = Radiometer3700("/dev/ttyr04")
rm2.info()
rm2.set("TG", 3)
rm2.set("bar", 2)                       # UNK
print("\n\n")

rm3 = RadiometerOphir("/dev/ttyr05")
rm3.info()
rm3.set("$DU", 1)
rm3.set("$AAA", 1)                      # UNK
print(f'DU = {rm3.get("$DU")}')
print(f'ZZ = {rm3.get("ZZ")}')          # UNK
print(f'BLA = {rm3.get("$BLA")}')       # UNK
print("\n\n")

