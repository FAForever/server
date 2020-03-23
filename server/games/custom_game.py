import time

from .game import Game, ValidityState, GameState
from server.rating import RatingType

from server.abc.base_game import InitMode
from server.decorators import with_logger


@with_logger
class CustomGame(Game):
    init_mode = InitMode.NORMAL_LOBBY

    async def rate_game(self):
        assert self.state is GameState.LIVE or self.state is GameState.ENDED

        limit = len(self.players) * 60
        if not self.enforce_rating and time.time() - self.launched_at < limit:
            await self.mark_invalid(ValidityState.TOO_SHORT)

        if self.validity is not ValidityState.VALID:
            return

        summary = self._get_rating_summary(RatingType.GLOBAL)
        await self.game_service.send_to_rating_service(summary)
