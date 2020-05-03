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

# Constants
FFA_TEAM = 1

# Credit to Axle for parameter changes,
# see: http://forums.faforever.com/viewtopic.php?f=45&t=11698#p119599
# Optimum values for ladder here, using them for global as well.
trueskill.setup(mu=1500, sigma=500, beta=240, tau=10, draw_probability=0.10)


class ConfigurationStore:
    def __init__(self):
        self._callbacks: Dict[str, Callable] = {}
        self._stored_values = {}
        self.refresh()

    def __getitem__(self, key: str) -> Any:
        try:
            return self._stored_values[key]
        except KeyError:
            raise KeyError(f"Unknown configuration variable {key}.")

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Direct value assignment for testing purposes only.
        """
        self._stored_values[key] = value

    def get_defaults(self) -> Dict[str, Any]:
        """
        Sets all config variables to their default values.
        Update here, if you want to change the default.
        """
        return {
            "CONFIGURATION_REFRESH_TIME": 300,
            "LOG_LEVEL": "DEBUG",
            "PROFILING_COUNT": 300,
            "PROFILING_DURATION": 2,
            "PROFILING_INTERVAL": -1,
            "CONTROL_SERVER_PORT": 4000,
            "METRICS_PORT": 8011,
            "ENABLE_METRICS": False,
            "DB_SERVER": "127.0.0.1",
            "DB_PORT": 3306,
            "DB_LOGIN": "root",
            "DB_PASSWORD": "banana",
            "DB_NAME": "faf",
            "API_CLIENT_ID": "client_id",
            "API_CLIENT_SECRET": "banana",
            "API_TOKEN_URI": "https://api.test.faforever.com/oauth/token",
            "API_BASE_URL": "https://api.test.faforever.com/",
            "WWW_URL": "https://www.faforever.com",
            "CONTENT_URL": "http://content.faforever.com",
            "FAF_POLICY_SERVER_BASE_URL": "http://faf-policy-server",
            "FORCE_STEAM_LINK_AFTER_DATE": 1536105599,  # 5 september 2018 by default
            "FORCE_STEAM_LINK": False,
            "NEWBIE_BASE_MEAN": 500,
            "NEWBIE_MIN_GAMES": 10,
            "TOP_PLAYER_MIN_RATING": 1600,
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_TOKEN": "",
            "TWILIO_TTL": 86400,
            "COTURN_HOSTS": [],
            "COTURN_KEYS": [],
            "GEO_IP_DATABASE_PATH": "GeoLite2-Country.mmdb",
            "GEO_IP_DATABASE_URL": "https://download.maxmind.com/app/geoip_download",
            "GEO_IP_LICENSE_KEY": "",
            "GEO_IP_DATABASE_MAX_AGE_DAYS": 22,
            "LADDER_ANTI_REPETITION_LIMIT": 3,
            "LADDER_SEARCH_EXPANSION_MAX": 0.25,
            "LADDER_SEARCH_EXPANSION_STEP": 0.05,
            # The maximum amount of time (in seconds) to wait between pops.
            "QUEUE_POP_TIME_MAX": 180,
            # The number of players we would like to have in the queue when it pops. The
            # queue pop time will be adjusted based on the current rate of players queuing
            # to try and hit this number.
            "QUEUE_POP_DESIRED_PLAYERS": 8,
            # How many previous queue sizes to consider
            "QUEUE_POP_TIME_MOVING_AVG_SIZE": 5,
        }

    def refresh(self) -> None:
        new_values = self.get_defaults()

        config_file = os.getenv("CONFIGURATION_FILE")
        if config_file is not None:
            with open(config_file) as f:
                new_values.update(yaml.safe_load(f))

        triggered_callback_keys = tuple(
            key
            for key in self._stored_values
            if key in self._callbacks
            and key in new_values
            and self._stored_values[key] != new_values[key]
        )

        self._stored_values.update(new_values)

        for key in triggered_callback_keys:
            self._dispatch_callback(key)

    def register_callback(self, key: str, callback: Callable) -> None:
        self._callbacks[key.upper()] = callback

    def _dispatch_callback(self, key: str) -> None:
        callback = self._callbacks[key]
        if asyncio.iscoroutinefunction(callback):
            asyncio.create_task(callback())
        else:
            callback()


def set_log_level():
    logger = logging.getLogger()
    logger.setLevel(config["LOG_LEVEL"])


config = ConfigurationStore()
config.register_callback("LOG_LEVEL", set_log_level)
