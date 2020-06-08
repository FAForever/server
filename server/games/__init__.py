from collections import namedtuple

from .coop import CoopGame
from .custom_game import CustomGame
from .game import Game
from .ladder_game import LadderGame
from .typedefs import FeaturedModType, GameState, VisibilityState

FeaturedMod = namedtuple(
    "FeaturedMod",
    "id name full_name description publish order"
)


__all__ = (
    "CoopGame",
    "CustomGame",
    "Game",
    "GameState",
    "LadderGame",
    "FeaturedMod",
    "FeaturedModType",
    "VisibilityState"
)
