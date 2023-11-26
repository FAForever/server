"""
Server config variables
"""

import asyncio
import logging
import os
import statistics
from typing import Callable

import trueskill
import yaml

from .decorators import with_logger

# Logging setup
TRACE = 5
logging.addLevelName(TRACE, "TRACE")
logging.getLogger("aiomeasures").setLevel(logging.INFO)
logging.getLogger("aio_pika").setLevel(logging.INFO)
logging.getLogger("aiormq").setLevel(logging.INFO)

# Constants
FFA_TEAM = 1

# Credit to Axle for parameter changes,
# see: http://forums.faforever.com/viewtopic.php?f=45&t=11698#p119599
# Optimum values for ladder here, using them for global as well.
trueskill.setup(mu=1500, sigma=500, beta=240, tau=10, draw_probability=0.10)
MAP_POOL_RATING_SELECTION_FUNCTIONS = {
    "mean": statistics.mean,
    "min": min,
    "max": max,
}


@with_logger
class ConfigurationStore:
    def __init__(self):
        """
        Change default values here.
        """
        self.CONFIGURATION_REFRESH_TIME = 300
        self.LISTEN = [
            {
                "ADDRESS": "",
                "PORT": 8001,
                "NAME": None,
                "PROTOCOL": "QDataStreamProtocol",
                "PROXY": False,
            },
            {
                "ADDRESS": "",
                "PORT": 8002,
                "NAME": None,
                "PROTOCOL": "SimpleJsonProtocol",
                "PROXY": False
            }
        ]
        self.LOG_LEVEL = "DEBUG"
        # Whether or not to use uvloop as a drop-in replacement for asyncio's
        # default event loop
        self.USE_UVLOOP = True
        self.PROFILING_COUNT = 300
        self.PROFILING_DURATION = 2
        self.PROFILING_INTERVAL = -1

        self.DIRTY_REPORT_INTERVAL = 1
        self.PING_INTERVAL = 45
        # How many seconds to wait for games to end before doing a hard shutdown.
        # If using kubernetes, you must set terminationGracePeriodSeconds
        # on the pod to be larger than this value. With docker compose, use
        # --timeout (-t) to set a longer timeout.
        self.SHUTDOWN_GRACE_PERIOD = 30 * 60
        self.SHUTDOWN_KICK_IDLE_PLAYERS = False

        self.CONTROL_SERVER_PORT = 4000
        self.HEALTH_SERVER_PORT = 2000
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
        # Location of the OAuth jwks
        self.HYDRA_JWKS_URI = "https://hydra.faforever.com/.well-known/jwks.json"

        self.MQ_USER = "faf-python-server"
        self.MQ_PASSWORD = "banana"
        self.MQ_SERVER = "127.0.0.1"
        self.MQ_PORT = 5672
        self.MQ_VHOST = "/faf-core"
        self.MQ_EXCHANGE_NAME = "faf-rabbitmq"

        self.WWW_URL = "https://www.faforever.com"
        self.CONTENT_URL = "http://content.faforever.com"
        self.FAF_POLICY_SERVER_BASE_URL = "http://faf-policy-server"
        self.USE_POLICY_SERVER = True

        self.ALLOW_PASSWORD_LOGIN = True
        # How many seconds a connection has to authenticate before being killed
        self.LOGIN_TIMEOUT = 5 * 60

        self.NEWBIE_BASE_MEAN = 500
        self.NEWBIE_MIN_GAMES = 10
        self.START_RATING_MEAN = 1500
        self.START_RATING_DEV = 500
        self.RATING_ADJUSTMENT_MAX_RATING = 1400
        self.HIGH_RATED_PLAYER_MIN_RATING = 1400
        self.TOP_PLAYER_MIN_RATING = 2000

        # Values for the custom (i.e. not trueskill) game quality metric used by the matchmaker
        self.MINIMUM_GAME_QUALITY = 0.4
        # Difference of cumulated rating of the teams
        self.MAXIMUM_RATING_IMBALANCE = 250
        # stdev of the ratings of all participating players
        self.MAXIMUM_RATING_DEVIATION = 250
        # Quality bonus for each failed matching attempt per full team
        self.TIME_BONUS = 0.01
        self.MAXIMUM_TIME_BONUS = 0.2
        self.NEWBIE_TIME_BONUS = 0.25
        self.MAXIMUM_NEWBIE_TIME_BONUS = 3.0
        self.MINORITY_BONUS = 1
        self.MINORITY_BONUS_RATING_RANGE = 1250

        self.GEO_IP_DATABASE_PATH = "GeoLite2-Country.mmdb"
        self.GEO_IP_DATABASE_URL = "https://download.maxmind.com/app/geoip_download"
        self.GEO_IP_LICENSE_KEY = ""
        self.GEO_IP_DATABASE_MAX_AGE_DAYS = 22

        self.LADDER_1V1_OUTCOME_OVERRIDE = True
        self.LADDER_ANTI_REPETITION_LIMIT = 2
        self.LADDER_SEARCH_EXPANSION_MAX = 0.25
        self.LADDER_SEARCH_EXPANSION_STEP = 0.05
        self.LADDER_TOP_PLAYER_SEARCH_EXPANSION_MAX = 0.3
        self.LADDER_TOP_PLAYER_SEARCH_EXPANSION_STEP = 0.15
        self.LADDER_NEWBIE_SEARCH_EXPANSION_MAX = 0.6
        self.LADDER_NEWBIE_SEARCH_EXPANSION_STEP = 0.1
        # The method for choosing map pool rating
        # Can be "mean", "min", or "max"
        self.MAP_POOL_RATING_SELECTION = "mean"
        # The maximum amount of time in seconds to wait between pops
        self.QUEUE_POP_TIME_MAX = 90
        # The minimum amount of time in seconds to wait between pops
        self.QUEUE_POP_TIME_MIN = 15
        # The number of possible matches we would like to have when the queue
        # pops. The queue pop time will be adjusted based on the current rate of
        # players queuing to try and hit this number.
        self.QUEUE_POP_DESIRED_MATCHES = 2.5
        # How many previous queue sizes to consider
        self.QUEUE_POP_TIME_MOVING_AVG_SIZE = 5

        self._defaults = {
            key: value
            for key, value in vars(self).items()
            if key.isupper()
        }

        self._callbacks: dict[str, Callable] = {}
        self.refresh()

    def refresh(self) -> None:
        new_values = self._defaults.copy()
        # Add fallback values from environment.
        # NOTE: Only works for string values!
        for key in new_values:
            value = os.getenv(key)
            if value is not None:
                new_values[key] = value

        config_file = os.getenv("CONFIGURATION_FILE")
        if config_file is not None:
            try:
                with open(config_file) as f:
                    new_values.update(yaml.safe_load(f))
            except FileNotFoundError:
                self._logger.warning(
                    "No configuration file found at %s",
                    config_file
                )
            except TypeError:
                self._logger.info(
                    "Configuration file at %s appears to be empty",
                    config_file
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
                    "New value for %s: %r -> %r", key, old_value, new_value
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
