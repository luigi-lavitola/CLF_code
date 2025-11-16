import yaml

class Configuration:

    def __init__(self):
        self.ports = {}
        self.motors = {}
        self.outlets = {}
        self.radiometers = {}
        self.parameters = {}

    def read(self):
        with open('conf/parameters.yml', 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                for k,v in doc.items():
                    self.parameters[k] = v

        with open('conf/ports.yml', 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                for k,v in doc.items():
                    self.ports[k] = v

        with open('conf/motors.yml', 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                for k,v in doc.items():
                    self.motors[k] = v

        with open('conf/outlets.yml', 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                for k,v in doc.items():
                    self.outlets[k] = v

        with open('conf/radiometers.yml', 'r') as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                for k,v in doc.items():
                    self.radiometers[k] = v

    def get_port_params(self, port):
        return self.ports.get(port, None)
    
    def __repr__(self):
        return f'ports: {self.ports}\nmotors: {self.motors}\noutlets: {self.outlets}\nradiometers: {self.radiometers}'


if __name__ == "__main__":
    cfg = Configuration()
    cfg.read()

    print(cfg)
    print(cfg.get_port_params("aaa"))
    print(cfg.get_port_params("FTDI:1"))

    for mname, mparams in cfg.motors.items():
        print(mname, mparams)

