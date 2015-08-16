from collections import namedtuple
from .gamesContainer import GamesContainer
from .ladderGamesContainer import Ladder1V1GamesContainer
from .coop import CoopGamesContainer
from .game import Game
from .ladderGame import Ladder1V1Game
from .custom_game import CustomGame

FeaturedMod = namedtuple('FeaturedMod', 'name full_name description publish')
