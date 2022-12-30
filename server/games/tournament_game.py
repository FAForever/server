import logging

from . import LadderGame
from .typedefs import GameType

logger = logging.getLogger(__name__)


class TournamentGame(LadderGame):
    """Class for tournament games"""

    game_type = GameType.TOURNAMENT
