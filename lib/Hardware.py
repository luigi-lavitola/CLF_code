"""
Hardware (FPGA board + firmware) profiles and time <-> tick conversions.

Every value written to or read from the FPGA timing registers is in ticks of the
FPGA system clock. The rest of the code works in physical units (seconds) and
converts here, with the profile of the hardware in use (`hw_version` of the site
in conf/parameters.yml).

Latencies come from the firmware (see README_timing.md of the firmware):
  Diode_Out (laser trigger) rises  D + E + trigger_latency_ticks  after the local PPS
  local PPS follows the GPS PPS by about  gps_to_local_ticks
  the shot period is  P + period_extra_ticks
with D = pps_delay, E = pulse_energy, P = pulse_period registers.
"""

import datetime
import logging
from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareProfile:
    version: int
    clk_hz: int
    trigger_latency_ticks: int      # local PPS -> Diode_Out rising edge, without D and E
    gps_to_local_ticks: int         # GPS PPS -> local PPS (nominal)
    period_extra_ticks: int         # firmware adds this to every shot period

    @property
    def tick_ns(self):
        return 1e9 / self.clk_hz

    def ticks(self, seconds):
        """Nearest number of ticks for a duration in seconds."""
        return int(round(seconds * self.clk_hz))

    def seconds(self, ticks):
        return ticks / self.clk_hz

    def pps_delay(self, trigger_s, energy_ticks):
        """pps_delay register value that puts the laser trigger (Diode_Out) at trigger_s
        after the GPS second, with the given pulse_energy register value."""
        d = (self.ticks(trigger_s) - energy_ticks
             - self.trigger_latency_ticks - self.gps_to_local_ticks)
        if d < 0:
            raise ValueError(f"trigger at {trigger_s * 1e3} ms is too early for pulse_energy "
                             f"{energy_ticks} ticks on hw v{self.version}")
        return d

    def trigger_time(self, pps_delay, energy_ticks):
        """Inverse of pps_delay(): laser trigger time in seconds after the GPS second."""
        return self.seconds(pps_delay + energy_ticks
                            + self.trigger_latency_ticks + self.gps_to_local_ticks)

    def period(self, period_s):
        """pulse_period register value for a shot period in seconds."""
        return max(self.ticks(period_s) - self.period_extra_ticks, 1)


PROFILES = {
    # 100 MHz VCXO disciplined by the PID; firmware before the 2026-10-20 Laser_controller fix
    # (period P+2, FIRE at D+3). PID setpoint 0x7FFD: local PPS ~3 ticks after GPS.
    1: HardwareProfile(version=1, clk_hz=100_000_000,
                       trigger_latency_ticks=8, gps_to_local_ticks=3, period_extra_ticks=2),
    # LEA-M8F 30.72 MHz x4; fixed Laser_controller (period P, FIRE at D).
    # After the (auto or forced) align the local PPS is 5 ticks after the first clock edge
    # that samples the GPS PPS (firmware tb_time_tag_align).
    2: HardwareProfile(version=2, clk_hz=122_880_000,
                       trigger_latency_ticks=5, gps_to_local_ticks=5, period_extra_ticks=0),
}

DEFAULT_VERSION = 1     # boards in the field before hw_version existed


def get_profile(params):
    """Profile for the site selected by params['identity'] (key 'hw_version', default 1)."""
    identity = str.lower(params['identity'])
    version = params[identity].get('hw_version')
    if version is None:
        logging.getLogger("run").warning(
            f"{identity}: 'hw_version' missing in parameters.yml, assuming {DEFAULT_VERSION}",
            extra={'classname': 'Hardware'})
        version = DEFAULT_VERSION
    if version not in PROFILES:
        raise ValueError(f"{identity}: unknown hw_version {version} (known: {sorted(PROFILES)})")
    return PROFILES[version]


def trigger_delay_ticks(params, run, energy_ticks):
    """pps_delay register for an FD/tank run ('fd' or 'tank') of the current site.

    New key  <run>_trigger_ms : laser trigger time after the GPS second, any hw_version.
    Old key  <run>_pps_delay  : raw register value, accepted only on hw_version 1.
    """
    hw = get_profile(params)
    site = params[str.lower(params['identity'])]
    if f'{run}_trigger_ms' in site:
        return hw.pps_delay(site[f'{run}_trigger_ms'] / 1e3, energy_ticks)
    if f'{run}_pps_delay' in site:
        if hw.version != 1:
            raise ValueError(f"'{run}_pps_delay' is in v1 ticks: use '{run}_trigger_ms' with hw_version {hw.version}")
        return site[f'{run}_pps_delay']
    raise KeyError(f"'{run}_trigger_ms' missing in parameters.yml")


FW_VERSION_REGISTER = 'fw_version'
FW_BUILD_REGISTER = 'fw_build'


def check_firmware(fpga, hw):
    """Compare the firmware version register with the configured profile.

    Firmware without the register reads 0 (v1, and v2 until the register is added):
    nothing can be checked then. Raises RuntimeError on a real mismatch."""
    fw = fpga.read_register(FW_VERSION_REGISTER)
    if fw == 0:
        return None
    if fw != hw.version:
        raise RuntimeError(f"FPGA firmware is v{fw} but hw_version is {hw.version} in parameters.yml")
    return fw


def decode_build_time(value):
    """USR_ACCESS TIMESTAMP word -> datetime of the bitstream build (local time of the build PC).

    Bits: day[31:27] month[26:23] year-2000[22:17] hour[16:12] minute[11:6] second[5:0].
    None for 0 (firmware without the register) or an impossible date."""
    if not value:
        return None
    try:
        return datetime.datetime(2000 + (value >> 17 & 0x3F), value >> 23 & 0xF, value >> 27 & 0x1F,
                                 value >> 12 & 0x1F, value >> 6 & 0x3F, value & 0x3F)
    except ValueError:
        return None


def firmware_build(fpga):
    """Build time of the bitstream running on the FPGA, None if unknown."""
    return decode_build_time(fpga.read_register(FW_BUILD_REGISTER))
