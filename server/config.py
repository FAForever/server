import logging
import os

import trueskill

# Logging setup
TRACE = 5
logging.addLevelName(TRACE, 'TRACE')
logging.getLogger('aiomeasures').setLevel(logging.INFO)

# Environment
LOG_LEVEL = logging.getLevelName(os.getenv('LOG_LEVEL', 'DEBUG'))

# Credit to Axle for parameter changes, see: http://forums.faforever.com/viewtopic.php?f=45&t=11698#p119599
# Optimum values for ladder here, using them for global as well.
trueskill.setup(mu=1500, sigma=500, beta=240, tau=10, draw_probability=0.10)

METRICS_PORT = int(os.getenv('METRICS_PORT', 8011))
ENABLE_METRICS = os.getenv('ENABLE_STATSD', 'false').lower() == 'true'

RULE_LINK = 'http://forums.faforever.com/forums/viewtopic.php?f=2&t=581#p5710'
WWW_URL = 'https://www.faforever.com'
CONTENT_URL = 'http://content.faforever.com'

DB_SERVER = os.getenv("DB_PORT_3306_TCP_ADDR", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT_3306_TCP_PORT", "3306"))
DB_LOGIN = os.getenv("FAF_DB_LOGIN", "root")
DB_PASSWORD = os.getenv("FAF_DB_PASSWORD", "banana")
DB_NAME = os.getenv("FAF_DB_NAME", "faf")

API_CLIENT_ID = os.getenv("API_CLIENT_ID", "client_id")
API_CLIENT_SECRET = os.getenv("API_CLIENT_SECRET", "banana")
API_TOKEN_URI = os.getenv("API_TOKEN_URI", "http://api.test.faforever.com/oauth/token")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api.test.faforever.com/")
USE_API = os.getenv("USE_API", 'true').lower() == 'true'

FAF_POLICY_SERVER_BASE_URL = os.getenv("FAF_POLICY_SERVER_BASE_URL", "http://faf-policy-server")
FORCE_STEAM_LINK_AFTER_DATE = int(os.getenv('FORCE_STEAM_LINK_AFTER_DATE', 1536105599))  # 5 september 2018 by default
FORCE_STEAM_LINK = os.getenv('FORCE_STEAM_LINK', 'false').lower() == 'true'

# How long we wait for a connection to read our messages before we consider
# it to be stalled. Stalled connections will be terminated if the max buffer
# size is reached.
CLIENT_STALL_TIME = int(os.getenv('CLIENT_STALL_TIME', 10))
# Maximum number of bytes we will allow a stalled connection to get behind
# before we terminate their connection.
CLIENT_MAX_WRITE_BUFFER_SIZE = int(os.getenv('CLIENT_MAX_WRITE_BUFFER_SIZE', 2**16))

NEWBIE_BASE_MEAN = int(os.getenv('NEWBIE_BASE_MEAN', 500))
NEWBIE_MIN_GAMES = int(os.getenv('NEWBIE_MIN_GAMES', 10))
TOP_PLAYER_MIN_RATING = int(os.getenv('TOP_PLAYER_MIN_RATING', 1600))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
TWILIO_TTL = os.getenv("TWILIO_TTL", 3600*24)

COTURN_HOSTS = list(filter(None, os.getenv('COTURN_HOSTS', "").split(',')))
COTURN_KEYS = list(filter(None, os.getenv('COTURN_KEYS', "").split(',')))

GEO_IP_DATABASE_PATH = os.getenv("GEO_IP_DATABASE_PATH", "GeoLite2-Country.mmdb")
GEO_IP_DATABASE_URL = os.getenv(
    "GEO_IP_DATABASE_URL",
    "https://download.maxmind.com/app/geoip_download"
)
GEO_IP_LICENSE_KEY = os.getenv("GEO_IP_LICENSE_KEY")
GEO_IP_DATABASE_MAX_AGE_DAYS = int(os.getenv('GEO_IP_DATABASE_MAX_AGE_DAYS', 22))

CONTROL_SERVER_PORT = int(os.getenv('CONTROL_SERVER_PORT', 4000))

LADDER_ANTI_REPETITION_LIMIT = int(os.getenv('LADDER_ANTI_REPETITION_LIMIT', 3))
LADDER_SEARCH_EXPANSION_MAX = float(os.getenv('LADDER_SEARCH_EXPANSION_MAX', 0.25))
LADDER_SEARCH_EXPANSION_STEP = float(os.getenv(
    'LADDER_SEARCH_EXPANSION_STEP',
    LADDER_SEARCH_EXPANSION_MAX / 5
))

# The maximum amount of time (in seconds) to wait between pops.
QUEUE_POP_TIME_MAX = int(os.getenv('QUEUE_POP_TIME_MAX', 60 * 3))
# The number of players we would like to have in the queue when it pops. The
# queue pop time will be adjusted based on the current rate of players queuing
# to try and hit this number.
QUEUE_POP_DESIRED_PLAYERS = int(os.getenv('QUEUE_POP_DESIRED_PLAYERS', 8))
# How many previous queue sizes to consider
QUEUE_POP_TIME_MOVING_AVG_SIZE = int(os.getenv('QUEUE_POP_TIME_MOVING_AVG_SIZE', 5))

# Team id that players in FFA mode are assigned to
FFA_TEAM = 1
