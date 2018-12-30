from time import sleep
from os import system
from .InstancePins import InstancePins
from .InstanceThreads import *
import config
from .Helper import *


class Controller:
    configuration = None
    # every Controller use the same GPIO Pin Instances
    Instances = InstancePins

    def set_master(self, state):
        if self.configuration["master_state"] != state:
            self.configuration["master_state"] = state
            self.update_all()

    def flip_master(self):
        self.configuration["master_state"] = not self.configuration["master_state"]
        self.update_all()

    def set_single(self, nr, state):
        self.configuration["selection"][self.configuration["selected"]]["state"][nr] = state
        self.update_single(nr)

    def flip_single(self, nr):
        self.configuration["selection"][self.configuration["selected"]]["state"][nr] = \
            not self.configuration["selection"][self.configuration["selected"]]["state"][nr]

        self.update_single(nr)

    def unify_group(self, group):
        value = 1
        for nr in group:
            if self.configuration["selection"][self.configuration["selected"]]["state"][nr]:
                value = 0
                break
        for nr in group:
            self.configuration["selection"][self.configuration["selected"]]["state"][nr] = value
            self.update_single(nr)

    def update_all(self):
        for nr in range(len(self.Instances)):
            self.update_single(nr)

    def update_single(self, nr):
        if self.configuration["master_state"] and \
                self.configuration["selection"][self.configuration["selected"]]["state"][nr]:

            self.Instances[nr].set_state(1)
        else:
            self.Instances[nr].set_state(0)

    def select_profile(self, nr):
        self.configuration["selected"] = nr


class ControllerMono(Controller):

    def __init__(self):
        self.configuration = dict(load_configuration("standard"))
        print(self.configuration)

    def update_single(self, nr):
        if self.configuration["master_state"] and \
                self.configuration["selection"][self.configuration["selected"]]["state"][nr]:

            self.Instances[nr].set_brightness(self.configuration["selection"][self.configuration["selected"]]["dc"][nr])
            self.Instances[nr].set_frequency(self.configuration["selection"][self.configuration["selected"]]["fq"][nr])
            self.Instances[nr].set_state(1)
        else:
            self.Instances[nr].set_state(0)

    def set_config_single(self, nr, value, conf):
        self.configuration["selection"][self.configuration["selected"]][conf][nr] = value
        self.update_single(nr)

    def set_config_group(self, group, value, conf):
        for nr in group:
            self.set_config_single(nr, value, conf)


class ControllerThreadsSingle(Controller):

    def __init__(self):
        # generate Thread instances for each pin in use
        for pinNr in range(config.ControllerConfig["PinCount"]):
            self.Instances[pinNr] = ThreadGPIOSingle(self.Instances[pinNr])
        self.configuration = dict(load_configuration("ThreadSingle"))
        print(self.configuration)

    def update_single(self, nr):
        if self.configuration["master_state"] and \
                self.configuration["selection"][self.configuration["selected"]]["state"][nr]:
            self.Instances[nr].set_config(self.configuration["profiles"][nr])
            if self.Instances[nr].isAlive():
                self.Instances[nr].restart()
            else:
                self.Instances[nr].start()
                self.Instances[nr].restart()
        else:
            stop_instance(self.Instances[nr])


class ControllerThreadsGroup(Controller):

    # constructor needs to be overworked
    def __init__(self):
        # generate Thread groups for each pin group in config.Default_Thread_Group
        '''
        count = 0
        for pinList in config.ControllerConfig[config.Default_Thread_Group]:
            tmp = []
            for pinNr in pinList:
                if pinNr < config.ControllerConfig["PinCount"]:
                    tmp.append(InstancePins[pinNr])
                    self.configuration["ThreadGroup"][pinNr] = count
                else:
                    raise ValueError("The pin(" + pinNr + ") in 'PinsInUse' is higher than 'PinCount'(" +
                                     config.ControllerConfig["PinCount"] + ")")
            self.Instances[count] = ThreadGPIOGroup(tmp)
            count += 1
        self.configuration = dict(load_configuration("group"))
        self.update_all()
        '''

    def update_single(self, pinNr):
        self.update_group(self.configuration["group"][pinNr])

    def update_group(self, groupNr):
        if self.configuration["master_state"]:
            tmpPinNrs = []
            pinNr = 0
            for groupStatus in self.configuration["group"]:
                if groupStatus == groupNr and \
                        not (CtrlLsp.configuration["master_state"] and CtrlLsp.configuration["state"][pinNr]):
                    tmpPinNrs.append(pinNr)
                pinNr += 1

            tmpInstances = []
            for pinNr in tmpPinNrs:
                if self.configuration["state"][pinNr]:
                    tmpInstances.append(self.Instances[pinNr])

            if len(tmpInstances) > 0:
                self.Instances[groupNr].set_instances(tmpInstances)
                self.Instances[groupNr].set_config(self.configuration["profiles"][groupNr])
                if self.Instances[groupNr].isAlive():
                    self.Instances[groupNr].restart()
                else:
                    self.Instances[groupNr].start()
                    self.Instances[groupNr].restart()
            else:
                stop_instance(self.Instances[groupNr])
        else:
            stop_instance(self.Instances[groupNr])

    def update_all(self):
        highestGroup = 0
        for groupStatus in self.configuration["group"]:
            if groupStatus > highestGroup:
                highestGroup = groupStatus
        for i in range(highestGroup + 1):
            self.update_group(i)


class ControllerLightshowpi(Controller):

    def __init__(self):
        self.configuration = dict(load_configuration("lsp"))
        print(self.configuration)

    def update_single(self, nr):
        self.update_all()

    def unify_group(self, group):
        value = 1
        for nr in group:
            if self.configuration["state"][nr]:
                value = 0
                break
        for nr in group:
            self.configuration["state"][nr] = value
        self.update_all()

    def update_all(self):
        if self.configuration["master_state"]:
            self.update_target()
            system("sudo systemctl restart lightshowpi")
        else:
            system("sudo systemctl kill lightshowpi")

    def update_target(self):
        try:
            with open(config.lsp_settings["target"], "w") as f:
                f.write("[hardware]\n")
                f.write("gpio_pins = " + self.get_lsp_pins() + "\n")
                f.write("pwm_range = " + self.get_settings("pwm_range") + "\n")
                if not self.get_settings("pin_modes") in ["onoff", "pwm"]:
                    self.set_settings("pin_modes", self.configuration["default"]["pin_modes"])
                f.write("pin_modes = " + self.get_settings("pin_modes") + "\n")
                f.write("[lightshow]\n")
                f.write("decay_factor = " + self.get_settings("decay_factor") + "\n")
                f.write("SD_low = " + self.get_settings("SD_low") + "\n")
                f.write("SD_high = " + self.get_settings("SD_high") + "\n")
                f.write("attenuate_pct = " + self.get_settings("attenuate_pct") + "\n")
                f.write("light_delay = " + self.get_settings("light_delay") + "\n")
                f.write(config.lsp_settings["stream"])
        except Exception:
            pass

    def get_settings(self, key):
        if self.configuration["profile"][self.configuration["selected_profile"]][key] is not None:
            return self.configuration["profile"][self.configuration["selected_profile"]][key]
        else:
            return self.configuration["default"][key]

    def set_settings(self, key, value):
        self.configuration["profile"][self.configuration["selected_profile"]][key] = value

    def get_lsp_pins(self):
        if config.lsp_settings["GPIO_mode"] == "BCM":
            return self.list_to_string(self.convert_to_WPI("BCMtoWPI"))
        if config.lsp_settings["GPIO_mode"] == "BOARD":
            return self.list_to_string(self.convert_to_WPI("BOARDtoWPI"))
        # User uses WiringPi
        return self.list_to_string(self.convert_to_pins())

    def convert_to_WPI(self, source):
        wpi = []
        pinNr = 0
        for value in self.configuration["state"]:
            if value:
                try:
                    wpi.append(config.lsp_settings[source][pinNr])
                except IndexError:
                    pass
            pinNr += 1
        return wpi

    def convert_to_pins(self):
        pins = []
        pinNr = 0
        for value in self.configuration["state"]:
            if value:
                try:
                    pins.append(pinNr)
                except IndexError:
                    pass
            pinNr += 1
        return pins

    @staticmethod
    def list_to_string(list):
        return str(list)[1:-1]


CtrlLsp = ControllerLightshowpi()
CtrlGroup = ControllerThreadsGroup()
CtrlSingle = ControllerThreadsSingle()
CtrlMono = ControllerMono()

CTRL = [CtrlMono, CtrlSingle, CtrlGroup, CtrlLsp]


class MasterController:
    configuration = None

    def __init__(self):
        self.configuration = load_configuration("master")

    def set_master(self, ctrl, state):
        if self.configuration["master_state"][ctrl] != state:
            self.configuration["master_state"][ctrl] = state
            self.update_all()

    def flip_master(self, ctrl):
        self.configuration["master_state"][ctrl] = not self.configuration["master_state"][ctrl]
        self.update_all()

    def set_single(self, ctrl, nr, state):
        self.configuration["state"][ctrl][nr] = state
        self.update_single(nr)

    def flip_single(self, ctrl, nr):
        self.configuration["state"][ctrl][nr] = not self.configuration["state"][ctrl][nr]
        self.update_single(nr)

    def unify_group(self, ctrl, group):
        value = 1
        for nr in group:
            if self.configuration["state"][ctrl][nr]:
                value = 0
                break
        for nr in group:
            self.configuration["state"][ctrl][nr] = value
            self.update_single(nr)

    def update_all(self):
        for nr in range(config.ControllerConfig["PinCount"]):
            self.update_single(nr)

    def update_single(self, nr):
        free = 1
        for highest_member in config.ControllerPriority:
            ctrl = config.Meta[highest_member]
            if free:
                if self.configuration["state"][ctrl][nr]:
                    CTRL[ctrl].set_single(nr, 1)
                    free = 0
                else:
                    CTRL[ctrl].set_single(nr, 0)
            else:
                CTRL[ctrl].set_single(nr, 0)

    def change_profile(self, ctrl, nr):
        save_json(self.configuration, ctrl, nr)
        self.configuration["selected"][ctrl] = nr
        self.configuration["state"][ctrl] = CTRL[ctrl].configuration["selection"][nr]
        CTRL[ctrl].select_profile(nr)
        self.update_all()


CtrlMaster = MasterController()

