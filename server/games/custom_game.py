import time
from typing import Optional

from server.decorators import with_logger
from server.games.validator import COMMON_RULES, NON_COOP_RULES, Validator
from server.rating import RatingType

from .game import Game
from .typedefs import GameType, InitMode, ValidityState


def minimum_length_rule(game: Game) -> Optional[ValidityState]:
    if game.launched_at is None:
        return

    limit = len(game.players) * 60
    if not game.enforce_rating and time.time() - game.launched_at < limit:
        return ValidityState.TOO_SHORT


@with_logger
class CustomGame(Game):
    init_mode = InitMode.NORMAL_LOBBY
    game_type = GameType.CUSTOM
    validator = Validator([
        *COMMON_RULES,
        *NON_COOP_RULES,
        minimum_length_rule
    ])

    def __init__(self, *args, **kwargs):
        new_kwargs = {
            "rating_type": RatingType.GLOBAL,
            "setup_timeout": 30
        }
        new_kwargs.update(kwargs)
        super().__init__(*args, **new_kwargs)
