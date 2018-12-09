import base64
import logging
import traceback

import rsa
import trueskill
import os
import sys

LOBBY_IP = os.getenv('LOBBY_IP', '37.58.123.3')
LOBBY_UDP_PORTS = [int(port) for port in os.getenv('LOBBY_UDP_PORTS', '7,53,67,80,123,194,547,3478,3535,6112,30351').split(',')]
LOBBY_NAT_ADDRESSES = list(map(lambda p: ('0.0.0.0', p), LOBBY_UDP_PORTS))

logging.getLogger('aiomeasures').setLevel(logging.INFO)

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
DB_NAME = os.getenv("FAF_DB_NAME", "faf_test")

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
