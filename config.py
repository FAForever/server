import logging
from configobj import ConfigObj
Config = ConfigObj("/etc/faforever/faforever.conf")

LOBBY_IP = Config.get('lobby_ip', '127.0.0.1')
LOBBY_UDP_PORT = Config.get('lobby_udp_port', 30351)

LOG_PATH = Config.get('logpath', './logs/')
LOG_LEVEL = eval('logging.{}'.format(Config.get('loglevel', 'DEBUG')))
logging.info("Setting default log level {}".format(LOG_LEVEL))
