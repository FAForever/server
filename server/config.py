import asyncio
import logging
import os
import yaml

from typing import Any, Callable, Dict

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
        self._callbacks: Dict[str, Callable[[Any, Any], None]] = {}
        self.refresh()

        # Constants
        self.FFA_TEAM = 1

    def refresh(self) -> None:
        print("refreshing")
        default_file = "default_conf.yaml"
        with open(default_file) as f:
            config_dict = yaml.safe_load(f)

        config_file = os.getenv("CONFIGURATION_FILE")
        if config_file is not None:
            with open(config_file) as f:
                config_dict.update(yaml.safe_load(f))

        for key, value in config_dict.items():
            self._handle_change(key.upper(), value)
            setattr(self, key.upper(), value)

    def register_callback(self, key: str, callback: Callable[[Any, Any], None]) -> None:
        self._callbacks[key.upper()] = callback

    def _handle_change(self, key: str, new_value: Any) -> None:
        if key not in self._callbacks or not hasattr(self, key):
            return

        old_value = getattr(self, key)
        if new_value == old_value:
            return

        callback = self._callbacks[key]
        if asyncio.iscoroutinefunction(callback):
            asyncio.create_task(callback(old_value, new_value))
        else:
            callback(old_value, new_value)


config = ConfigurationStore()
