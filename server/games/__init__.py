from collections import namedtuple
from .ladder_service import LadderService
from .game import Game
from .ladderGame import Ladder1V1Game
from .custom_game import CustomGame

FeaturedMod = namedtuple('FeaturedMod', 'name full_name description publish')
