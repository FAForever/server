import time

from .game import Game, ValidityState
from server.rating import RatingType

from server.abc.base_game import InitMode
from server.decorators import with_logger


@with_logger
class CustomGame(Game):
    init_mode = InitMode.NORMAL_LOBBY

    async def rate_game(self):
        limit = len(self.players) * 60
        if not self.enforce_rating and time.time() - self.launched_at < limit:
            await self.mark_invalid(ValidityState.TOO_SHORT)
        if self.validity == ValidityState.VALID:
            await self.game_service.send_to_rating_service(self, RatingType.GLOBAL)
