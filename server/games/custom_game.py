import time

from .game import Game, ValidityState
from server.rating import RatingType

from server.abc.base_game import InitMode
from server.decorators import with_logger


@with_logger
class CustomGame(Game):
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, id_, *args, **kwargs):
        super(self.__class__, self).__init__(
            id_, *args, **kwargs, rating_type=RatingType.GLOBAL
        )

    async def _run_pre_rate_validity_checks(self):
        limit = len(self.players) * 60
        if not self.enforce_rating and time.time() - self.launched_at < limit:
            await self.mark_invalid(ValidityState.TOO_SHORT)
