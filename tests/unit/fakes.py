"""Minimal stand-ins for the devices in DeviceCollection, recording what the code does."""


class FakeOutlet:
    def __init__(self, name, events):
        self.name = name
        self.events = events
        self.state = False

    def on(self):
        self.state = True
        self.events.append(("outlet_on", self.name))
        return True

    def off(self):
        self.state = False
        self.events.append(("outlet_off", self.name))
        return True

    def status(self):
        return self.state


class FakeFPGA:
    def __init__(self, events, dio=None, registers=None):
        self.events = events
        self.dio = dict(dio or {})
        self.registers = dict(registers or {})

    def read_dio(self, name):
        return self.dio.get(name, False)

    def write_dio(self, name, value):
        self.dio[name] = bool(value)
        self.events.append(("dio", name, bool(value)))

    read_bit = read_dio
    write_bit = write_dio

    def read_register(self, name):
        return self.registers.get(name, 0)

    def write_register(self, name, value):
        self.registers[name] = value


class FakeLaser:
    def __init__(self, events):
        self.events = events

    def standby(self):
        self.events.append(("laser", "standby"))

    def set_mode(self, **kwargs):
        self.events.append(("laser", "set_mode"))

    def warmup(self):
        self.events.append(("laser", "warmup"))

    def fire_auth(self):
        return True

    def temperature(self):
        return (300, 200, 200)

    def fire(self):
        self.events.append(("laser", "fire"))
        return 0


class FakeRadiometer:
    def setup(self):
        pass

    def read_power(self):
        return 1.0


class FakeMotor:
    ecal_position = 0
    pcal_position = 0

    def init(self):
        pass

    def move_Neg0(self):
        pass

    def set_ABSzero(self):
        pass

    def move_ABS(self, pos):
        pass


class FakeDC:
    def __init__(self, dio=None, registers=None):
        self.events = []
        self.fpga = FakeFPGA(self.events, dio, registers)
        self.laser = FakeLaser(self.events)
        self.outlets = {}

    def get_outlet(self, name):
        if name not in self.outlets:
            self.outlets[name] = FakeOutlet(name, self.events)
        return self.outlets[name]

    def get_radiometer(self, name):
        return FakeRadiometer()

    def get_motor(self, name):
        return FakeMotor()
