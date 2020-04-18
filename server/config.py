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

    def refresh(self):
        config_file = os.getenv("CONFIGURATION_FILE", "conf.yaml")
        with open(config_file, "r") as f:
            config_dict = yaml.safe_load(f)

        for key, value in config_dict.items():
            setattr(self, key.upper(), value)


config = ConfigurationStore()

# FIXME
# need to update readme
