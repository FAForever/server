import logging


import trueskill
from configobj import ConfigObj
import os

Config = ConfigObj("/etc/faforever/faforever.conf").get('global', {})

LOBBY_IP = os.getenv('LOBBY_IP', '37.58.123.3')
LOBBY_UDP_PORTS = [int(port) for port in os.getenv('LOBBY_UDP_PORTS', '7,53,67,80,123,194,547,3478,3535,6112,30351').split(',')]
LOBBY_NAT_ADDRESSES = list(map(lambda p: ('0.0.0.0', p), LOBBY_UDP_PORTS))

LOG_PATH = Config.get('logpath', './logs/')
LOG_LEVEL = eval('logging.{}'.format(Config.get('loglevel', 'DEBUG')))

# Use this for making Qt find plugins (eq. qmysql)
LIBRARY_PATH = Config.get('library_path', None)

logging.info("Setting default log level {}".format(LOG_LEVEL))

logging.getLogger('aiomeasures').setLevel(logging.INFO)

logging.getLogger().setLevel(logging.DEBUG)

trueskill.setup(mu=1500, sigma=500, beta=250, tau=5, draw_probability=0.10)

STATSD_SERVER = os.getenv('STATSD_SERVER', '127.0.0.1:8125')

RULE_LINK = Config.get('rule_url', 'http://forums.faforever.com/forums/viewtopic.php?f=2&t=581#p5710')
WIKI_LINK = Config.get('wiki_url', 'http://wiki.faforever.com')
APP_URL = Config.get('app_url', 'http://app.faforever.com')
CONTENT_URL = Config.get('content_url', 'http://content.faforever.com')
CONTENT_PATH = Config.get('content_path', '/content/')  # Must have trailing slash

LADDER_SEASON = Config.get('ladder_season', "ladder_season_5")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.mandrillapp.com")
SMTP_PORT = os.getenv("SMTP_PORT", 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "admin@faforever.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
