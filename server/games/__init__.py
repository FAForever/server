from collections import namedtuple
from .ladder_service import LadderService
from .game import Game
from .ladder_game import LadderGame
from .custom_game import CustomGame

FeaturedMod = namedtuple('FeaturedMod', 'name full_name description publish')
