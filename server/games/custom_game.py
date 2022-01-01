import time

from server.decorators import with_logger
from server.rating import RatingType

from .game import Game
from .typedefs import GameType, ValidityState


@with_logger
class CustomGame(Game):
    game_type = GameType.CUSTOM

    def __init__(self, id_, *args, **kwargs):
        new_kwargs = {
            "rating_type": RatingType.GLOBAL,
            "setup_timeout": 30
        }
        new_kwargs.update(kwargs)
        super().__init__(id_, *args, **new_kwargs)

    async def _run_pre_rate_validity_checks(self):
        limit = len(self.players) * 60
        if not self.enforce_rating and time.time() - self.launched_at < limit:
            await self.mark_invalid(ValidityState.TOO_SHORT)
