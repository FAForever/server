import logging

import trueskill
import os

# Logging
TRACE = 5
LOG_LEVEL = int(os.getenv('LOG_LEVEL', logging.DEBUG))
logging.addLevelName(TRACE, 'TRACE')
logging.getLogger('aiomeasures').setLevel(logging.INFO)

# Environment

# Credit to Axle for parameter changes, see: http://forums.faforever.com/viewtopic.php?f=45&t=11698#p119599
# Optimum values for ladder here, using them for global as well.
trueskill.setup(mu=1500, sigma=500, beta=240, tau=10, draw_probability=0.10)

STATSD_SERVER = os.getenv('STATSD_SERVER', '127.0.0.1:8125')
ENABLE_STATSD = os.getenv('ENABLE_STATSD', 'false').lower() == 'true'

RULE_LINK = 'http://forums.faforever.com/forums/viewtopic.php?f=2&t=581#p5710'
WIKI_LINK = 'http://wiki.faforever.com'
WWW_URL = 'https://www.faforever.com'
CONTENT_URL = 'http://content.faforever.com'
CONTENT_PATH = '/content/'  # Must have trailing slash

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.mandrillapp.com")
SMTP_PORT = os.getenv("SMTP_PORT", 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "admin@faforever.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

MANDRILL_API_KEY = os.getenv("MANDRILL_API_KEY", '')
MANDRILL_API_URL = os.getenv("MANDRILL_API_URL", 'https://mandrillapp.com/api/1.0')

VERIFICATION_HASH_SECRET = os.getenv("VERIFICATION_HASH_SECRET", "")
VERIFICATION_SECRET_KEY = os.getenv("VERIFICATION_SECRET_KEY", "")

PRIVATE_KEYS = []
AES_KEY_BASE64_SIZES = []
DB_SERVER = os.getenv("DB_PORT_3306_TCP_ADDR", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT_3306_TCP_PORT", "3306"))
DB_LOGIN = os.getenv("FAF_DB_LOGIN", "root")
DB_PASSWORD = os.getenv("FAF_DB_PASSWORD", "banana")
DB_NAME = os.getenv("FAF_DB_NAME", "faf")

CHALLONGE_KEY = "challonge_key"
CHALLONGE_USER = "challonge_user"

API_CLIENT_ID = os.getenv("API_CLIENT_ID", "client_id")
API_CLIENT_SECRET = os.getenv("API_CLIENT_SECRET", "banana")
API_TOKEN_URI = os.getenv("API_TOKEN_URI", "http://api.test.faforever.com/oauth/token")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api.test.faforever.com/")
USE_API = os.getenv("USE_API", 'true').lower() == 'true'

FAF_POLICY_SERVER_BASE_URL = os.getenv("FAF_POLICY_SERVER_BASE_URL", "http://faf-policy-server")
FORCE_STEAM_LINK_AFTER_DATE = int(os.getenv('FORCE_STEAM_LINK_AFTER_DATE', 1536105599)) # 5 september 2018 by default
FORCE_STEAM_LINK = os.getenv('FORCE_STEAM_LINK', 'false').lower() == 'true'

NEWBIE_BASE_MEAN = int(os.getenv('NEWBIE_BASE_MEAN', 500))
NEWBIE_MIN_GAMES = int(os.getenv('NEWBIE_MIN_GAMES', 10))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
TWILIO_TTL = os.getenv("TWILIO_TTL", 3600*24)

COTURN_HOSTS = os.getenv('COTURN_HOSTS', "").split(',')
COTURN_KEYS = os.getenv('COTURN_KEYS', "").split(',')

GEO_IP_DATABASE_PATH = os.getenv("GEO_IP_DATABASE_PATH", "GeoLite2-Country.mmdb")
GEO_IP_DATABASE_URL = os.getenv(
    "GEO_IP_DATABASE_URL",
    "http://geolite.maxmind.com/download/geoip/database/GeoLite2-Country.mmdb.gz"
)
GEO_IP_DATABASE_MAX_AGE_DAYS = int(os.getenv('GEO_IP_DATABASE_MAX_AGE_DAYS', 22))

CONTROL_SERVER_PORT = int(os.getenv('CONTROL_SERVER_PORT', 4000))

LADDER_ANTI_REPETITION_LIMIT = int(os.getenv('LADDER_ANTI_REPETITION_LIMIT', 3))
