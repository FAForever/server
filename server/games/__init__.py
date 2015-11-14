from collections import namedtuple
from .ladder_service import LadderService
from .game import Game
from .ladder_game import LadderGame
from .coop import CoopGame
from .custom_game import CustomGame

FeaturedMod = namedtuple('FeaturedMod', 'id name full_name description publish')
