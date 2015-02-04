__version__ = "1.0"
__author__ = "russ-"

from . import tournaments, matches, participants
from .api import set_credentials, get_credentials, fetch, ChallongeException
