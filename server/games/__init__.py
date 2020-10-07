from collections import namedtuple

from .coop import CoopGame
from .custom_game import CustomGame
from .game import Game, GameError
from .ladder_game import LadderGame
from .typedefs import (
    FeaturedModType,
    GameState,
    ValidityState,
    Victory,
    VisibilityState
)

FeaturedMod = namedtuple(
    "FeaturedMod",
    "id name full_name description publish order"
)


__all__ = (
    "CoopGame",
    "CustomGame",
    "FeaturedMod",
    "FeaturedModType",
    "Game",
    "GameError",
    "GameState",
    "LadderGame",
    "ValidityState",
    "Victory",
    "VisibilityState",
)
