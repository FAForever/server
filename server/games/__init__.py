from collections import namedtuple

from .coop import CoopGame
from .custom_game import CustomGame
from .game import Game
from .ladder_game import LadderGame

FeaturedMod = namedtuple('FeaturedMod', 'id name full_name description publish order')
