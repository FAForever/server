import base64
import logging

import rsa
import trueskill
import os

LOBBY_IP = os.getenv('LOBBY_IP', '37.58.123.3')
LOBBY_UDP_PORTS = [int(port) for port in os.getenv('LOBBY_UDP_PORTS', '7,53,67,80,123,194,547,3478,3535,6112,30351').split(',')]
LOBBY_NAT_ADDRESSES = list(map(lambda p: ('0.0.0.0', p), LOBBY_UDP_PORTS))

logging.getLogger('aiomeasures').setLevel(logging.INFO)

logging.getLogger().setLevel(logging.DEBUG)

trueskill.setup(mu=1500, sigma=500, beta=250, tau=5, draw_probability=0.10)

STATSD_SERVER = os.getenv('STATSD_SERVER', '127.0.0.1:8125')

RULE_LINK = 'http://forums.faforever.com/forums/viewtopic.php?f=2&t=581#p5710'
WIKI_LINK = 'http://wiki.faforever.com'
APP_URL = 'http://app.faforever.com'
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

try:
    PRIVATE_KEY = rsa.PrivateKey.load_pkcs1(base64.b64decode(os.getenv("FAF_PRIVATE_KEY")), format='DER')
except:
    PRIVATE_KEY = None

DB_SERVER = os.getenv("DB_PORT_3306_TCP_ADDR", "localhost")
DB_PORT = int(os.getenv("DB_PORT_3306_TCP_PORT", "3306"))
DB_LOGIN = os.getenv("FAF_DB_LOGIN", "root")
DB_PASSWORD = os.getenv("FAF_DB_PASSWORD", "banana")
DB_NAME = os.getenv("FAF_DB_NAME", "faf_test")

CHALLONGE_KEY = "challonge_key"
CHALLONGE_USER = "challonge_user"

API_CLIENT_ID = os.getenv("API_CLIENT_ID", "6ccaf75b-a1f3-48be-bac3-4e9ffba81eb7")
API_CLIENT_SECRET = os.getenv("API_CLIENT_SECRET", "banana")
API_TOKEN_URI = os.getenv("API_TOKEN_URI", "http://api.dev.faforever.com/jwt/auth")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api.dev.faforever.com/jwt")
