import asyncio
import logging
import os
from typing import Callable, Dict

import yaml

import trueskill

from .decorators import with_logger

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


@with_logger
class ConfigurationStore:
    def __init__(self):
        """
        Change default values here.
        """
        self.CONFIGURATION_REFRESH_TIME = 300
        self.LOG_LEVEL = "DEBUG"
        self.PROFILING_COUNT = 300
        self.PROFILING_DURATION = 2
        self.PROFILING_INTERVAL = -1

        self.CONTROL_SERVER_PORT = 4000
        self.METRICS_PORT = 8011
        self.ENABLE_METRICS = False

        self.DB_SERVER = "127.0.0.1"
        self.DB_PORT = 3306
        self.DB_LOGIN = "root"
        self.DB_PASSWORD = "banana"
        self.DB_NAME = "faf"

        self.API_CLIENT_ID = "client_id"
        self.API_CLIENT_SECRET = "banana"
        self.API_TOKEN_URI = "https://api.test.faforever.com/oauth/token"
        self.API_BASE_URL = "https://api.test.faforever.com/"
        self.USE_API = True

        self.WWW_URL = "https://www.faforever.com"
        self.CONTENT_URL = "http://content.faforever.com"
        self.FAF_POLICY_SERVER_BASE_URL = "http://faf-policy-server"

        self.FORCE_STEAM_LINK_AFTER_DATE = 1536105599  # 5 september 2018 by default
        self.FORCE_STEAM_LINK = False

        self.NEWBIE_BASE_MEAN = 500
        self.NEWBIE_MIN_GAMES = 10
        self.TOP_PLAYER_MIN_RATING = 1600

        self.TWILIO_ACCOUNT_SID = ""
        self.TWILIO_TOKEN = ""
        self.TWILIO_TTL = 86400
        self.COTURN_HOSTS = []
        self.COTURN_KEYS = []

        self.GEO_IP_DATABASE_PATH = "GeoLite2-Country.mmdb"
        self.GEO_IP_DATABASE_URL = "https://download.maxmind.com/app/geoip_download"
        self.GEO_IP_LICENSE_KEY = ""
        self.GEO_IP_DATABASE_MAX_AGE_DAYS = 22

        self.LADDER_ANTI_REPETITION_LIMIT = 3
        self.LADDER_SEARCH_EXPANSION_MAX = 0.25
        self.LADDER_SEARCH_EXPANSION_STEP = 0.05
        # The maximum amount of time in seconds) to wait between pops.
        self.QUEUE_POP_TIME_MAX = 180
        # The number of players we would like to have in the queue when it pops. The
        # queue pop time will be adjusted based on the current rate of players queuing
        # to try and hit this number.
        self.QUEUE_POP_DESIRED_PLAYERS = 8
        # How many previous queue sizes to consider
        self.QUEUE_POP_TIME_MOVING_AVG_SIZE = 5

        self._defaults = {
            key: value for key, value in vars(self).items() if key.isupper()
        }

        self._callbacks: Dict[str, Callable] = {}
        self.refresh()

    def refresh(self) -> None:
        new_values = self._defaults.copy()

        config_file = os.getenv("CONFIGURATION_FILE")
        if config_file is not None:
            try:
                with open(config_file) as f:
                    new_values.update(yaml.safe_load(f))
            except FileNotFoundError:
                self._logger.info("No configuration file found at %s", config_file)
            except TypeError:
                self._logger.info(
                    "Configuration file at %s appears to be empty", config_file
                )

        triggered_callback_keys = tuple(
            key
            for key in new_values
            if key in self._callbacks
            and hasattr(self, key)
            and getattr(self, key) != new_values[key]
        )

        for key, new_value in new_values.items():
            old_value = getattr(self, key, None)
            if new_value != old_value:
                self._logger.info(
                    "New value for %s: %s -> %s", key, old_value, new_value
                )
            setattr(self, key, new_value)

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
    logger.setLevel(config.LOG_LEVEL)


config = ConfigurationStore()
config.register_callback("LOG_LEVEL", set_log_level)
