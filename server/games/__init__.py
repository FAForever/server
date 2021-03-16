from typing import NamedTuple

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


class FeaturedMod(NamedTuple):
    id: int
    name: str
    full_name: str
    description: str
    publish: bool
    order: int


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
