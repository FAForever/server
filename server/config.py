import logging
import os

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

        self.WWW_URL = "https://www.faforever.com"
        self.CONTENT_URL = "http://content.faforever.com"

        # Team id that players in FFA mode are assigned to
        self.FFA_TEAM = 1

    def refresh(self):
        self.CONFIGURATION_REFRESH_TIME = int(
            os.getenv("CONFIGURATION_REFRESH_TIME", 60 * 5)
        )

        # Environment
        self.LOG_LEVEL = logging.getLevelName(os.getenv("LOG_LEVEL", "DEBUG"))
        self.PROFILING_INTERVAL = int(os.getenv("PROFILING_INTERVAL", -1))

        self.METRICS_PORT = int(os.getenv("METRICS_PORT", 8011))
        self.ENABLE_METRICS = os.getenv("ENABLE_STATSD", "false").lower() == "true"

        self.DB_SERVER = os.getenv("DB_PORT_3306_TCP_ADDR", "127.0.0.1")
        self.DB_PORT = int(os.getenv("DB_PORT_3306_TCP_PORT", "3306"))
        self.DB_LOGIN = os.getenv("FAF_DB_LOGIN", "root")
        self.DB_PASSWORD = os.getenv("FAF_DB_PASSWORD", "banana")
        self.DB_NAME = os.getenv("FAF_DB_NAME", "faf")

        self.API_CLIENT_ID = os.getenv("API_CLIENT_ID", "client_id")
        self.API_CLIENT_SECRET = os.getenv("API_CLIENT_SECRET", "banana")
        self.API_TOKEN_URI = os.getenv(
            "API_TOKEN_URI", "https://api.test.faforever.com/oauth/token"
        )
        self.API_BASE_URL = os.getenv("API_BASE_URL", "https://api.test.faforever.com/")
        self.USE_API = os.getenv("USE_API", "true").lower() == "true"

        self.FAF_POLICY_SERVER_BASE_URL = os.getenv(
            "FAF_POLICY_SERVER_BASE_URL", "http://faf-policy-server"
        )
        self.FORCE_STEAM_LINK_AFTER_DATE = int(
            os.getenv("FORCE_STEAM_LINK_AFTER_DATE", 1536105599)
        )  # 5 september 2018 by default
        self.FORCE_STEAM_LINK = os.getenv("FORCE_STEAM_LINK", "false").lower() == "true"

        self.NEWBIE_BASE_MEAN = int(os.getenv("NEWBIE_BASE_MEAN", 500))
        self.NEWBIE_MIN_GAMES = int(os.getenv("NEWBIE_MIN_GAMES", 10))
        self.TOP_PLAYER_MIN_RATING = int(os.getenv("TOP_PLAYER_MIN_RATING", 1600))

        self.TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
        self.TWILIO_TTL = os.getenv("TWILIO_TTL", 3600 * 24)

        self.COTURN_HOSTS = list(filter(None, os.getenv("COTURN_HOSTS", "").split(",")))
        self.COTURN_KEYS = list(filter(None, os.getenv("COTURN_KEYS", "").split(",")))

        self.GEO_IP_DATABASE_PATH = os.getenv(
            "GEO_IP_DATABASE_PATH", "GeoLite2-Country.mmdb"
        )
        self.GEO_IP_DATABASE_URL = os.getenv(
            "GEO_IP_DATABASE_URL", "https://download.maxmind.com/app/geoip_download"
        )
        self.GEO_IP_LICENSE_KEY = os.getenv("GEO_IP_LICENSE_KEY")
        self.GEO_IP_DATABASE_MAX_AGE_DAYS = int(
            os.getenv("GEO_IP_DATABASE_MAX_AGE_DAYS", 22)
        )

        self.CONTROL_SERVER_PORT = int(os.getenv("CONTROL_SERVER_PORT", 4000))

        self.LADDER_ANTI_REPETITION_LIMIT = int(
            os.getenv("LADDER_ANTI_REPETITION_LIMIT", 3)
        )
        self.LADDER_SEARCH_EXPANSION_MAX = float(
            os.getenv("LADDER_SEARCH_EXPANSION_MAX", 0.25)
        )
        self.LADDER_SEARCH_EXPANSION_STEP = float(
            os.getenv(
                "LADDER_SEARCH_EXPANSION_STEP", self.LADDER_SEARCH_EXPANSION_MAX / 5
            )
        )

        # The maximum amount of time (in seconds) to wait between pops.
        self.QUEUE_POP_TIME_MAX = int(os.getenv("QUEUE_POP_TIME_MAX", 60 * 3))
        # The number of players we would like to have in the queue when it pops. The
        # queue pop time will be adjusted based on the current rate of players queuing
        # to try and hit this number.
        self.QUEUE_POP_DESIRED_PLAYERS = int(os.getenv("QUEUE_POP_DESIRED_PLAYERS", 8))
        # How many previous queue sizes to consider
        self.QUEUE_POP_TIME_MOVING_AVG_SIZE = int(
            os.getenv("QUEUE_POP_TIME_MOVING_AVG_SIZE", 5)
        )


config = ConfigurationStore()
