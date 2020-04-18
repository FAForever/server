import logging
import os
import yaml

import trueskill

# Logging setup
TRACE = 5
logging.addLevelName(TRACE, "TRACE")
logging.getLogger("aiomeasures").setLevel(logging.INFO)

# Credit to Axle for parameter changes,
# see: http://forums.faforever.com/viewtopic.php?f=45&t=11698#p119599
# Optimum values for ladder here, using them for global as well.
trueskill.setup(mu=1500, sigma=500, beta=240, tau=10, draw_probability=0.10)


class ConfigurationStore:
    def __init__(self):
        self.refresh()

        # Constants
        self.FFA_TEAM = 1

    def refresh(self):
        default_file = "default_conf.yaml"
        with open(default_file) as f:
            config_dict = yaml.safe_load(f)

        config_file = os.getenv("CONFIGURATION_FILE")
        if config_file is not None:
            with open(config_file) as f:
                config_dict.update(yaml.safe_load(f))

        for key, value in config_dict.items():
            setattr(self, key.upper(), value)


config = ConfigurationStore()
