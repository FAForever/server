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
PRIVATE_KEY_BLOBS = os.getenv("FAF_PRIVATE_KEY", '').split(';')
print('CONFIG: {} private key blobs found in env'.format(len(PRIVATE_KEY_BLOBS)), file=sys.stderr)
for KEYBLOB in PRIVATE_KEY_BLOBS:
    try:
        PRIVATE_KEY = rsa.PrivateKey.load_pkcs1(base64.b64decode(KEYBLOB), format='DER')
        keybits = PRIVATE_KEY.n.bit_length() + 7 - ((PRIVATE_KEY.n.bit_length() + 7)%8) # round up to multiple of 8 (byte)
        _aes_key_base64_size = 4*keybits/24
        _aes_key_base64_size = int(_aes_key_base64_size + 3 - ((_aes_key_base64_size + 3)%4)) # round to multiple of 4
        PRIVATE_KEYS.append(PRIVATE_KEY)
        AES_KEY_BASE64_SIZES.append(_aes_key_base64_size)
        print('CONFIG: Loaded {}bit rsa key, aes key size {}'.format(keybits, _aes_key_base64_size), file=sys.stderr)
    except:
        print(traceback.format_exc(), file=sys.stderr)
print('CONFIG: {} private keys loaded'.format(len(PRIVATE_KEYS)), file=sys.stderr)

DB_SERVER = os.getenv("DB_PORT_3306_TCP_ADDR", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT_3306_TCP_PORT", "3306"))
DB_LOGIN = os.getenv("FAF_DB_LOGIN", "root")
DB_PASSWORD = os.getenv("FAF_DB_PASSWORD", "banana")
DB_NAME = os.getenv("FAF_DB_NAME", "faf_test")

CHALLONGE_KEY = "challonge_key"
CHALLONGE_USER = "challonge_user"

API_CLIENT_ID = os.getenv("API_CLIENT_ID", "6ccaf75b-a1f3-48be-bac3-4e9ffba81eb7")
API_CLIENT_SECRET = os.getenv("API_CLIENT_SECRET", "banana")
API_TOKEN_URI = os.getenv("API_TOKEN_URI", "https://api.dev.faforever.com/jwt/auth")
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.dev.faforever.com/jwt")
