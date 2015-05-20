import logging

import trueskill
from configobj import ConfigObj

Config = ConfigObj("/etc/faforever/faforever.conf").get('global', {})

LOBBY_IP = Config.get('lobby_ip', '127.0.0.1')
LOBBY_UDP_PORT = Config.get('lobby_udp_port', 30351)

LOG_PATH = Config.get('logpath', './logs/')
LOG_LEVEL = eval('logging.{}'.format(Config.get('loglevel', 'DEBUG')))

# Use this for making Qt find plugins (eq. qmysql)
LIBRARY_PATH = Config.get('library_path', None)

logging.info("Setting default log level {}".format(LOG_LEVEL))
logging.getLogger('quamash').setLevel(logging.INFO)
logging.getLogger().setLevel(logging.DEBUG)

trueskill.setup(mu=1500, sigma=500, beta=250, tau=5, draw_probability=0.10)

WIKI_LINK = Config.get('wiki_url', 'http://wiki.faforever.com')
