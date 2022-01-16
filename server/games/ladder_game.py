import asyncio
import logging
from typing import Optional

from server.config import config
from server.players import Player

from .game import Game
from .game_results import ArmyOutcome, GameOutcome
from .typedefs import GameState, GameType, InitMode

logger = logging.getLogger(__name__)


class GameClosedError(Exception):
    """
    The game has been closed during the setup phase
    """

    def __init__(self, player: Player, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player


class LadderGame(Game):
    """Class for 1v1 ladder games"""

    init_mode = InitMode.AUTO_LOBBY
    game_type = GameType.MATCHMAKER

    def __init__(self, id_, *args, **kwargs):
        super().__init__(id_, *args, **kwargs)
        self._launch_future = asyncio.Future()

    async def wait_hosted(self, timeout: float):
        return await asyncio.wait_for(
            self._hosted_event.wait(),
            timeout=timeout
        )

    async def wait_launched(self, timeout: float):
        return await asyncio.wait_for(
            self._launch_future,
            timeout=timeout
        )

    async def launch(self):
        await super().launch()
        self._launch_future.set_result(None)

    async def check_game_finish(self, player):
        if not self._launch_future.done() and (
            self.state in (GameState.INITIALIZING, GameState.LOBBY)
        ):
            self._launch_future.set_exception(GameClosedError(player))

        await super().check_game_finish(player)

    def is_winner(self, player: Player) -> bool:
        return self.get_player_outcome(player) is ArmyOutcome.VICTORY

    def get_army_score(self, army: int) -> int:
        """
        We override this function so that ladder game scores are only reported
        as 1 for win and 0 for anything else.
        """
        return self._results.victory_only_score(army)

    def _outcome_override_hook(self) -> Optional[list[GameOutcome]]:
        if not config.LADDER_1V1_OUTCOME_OVERRIDE or len(self.players) > 2:
            return None
        team_sets = self.get_team_sets()
        army_scores = [
            self._results.score(self.get_player_option(team_set.pop().id, "Army"))
            for team_set in team_sets
        ]
        if army_scores[0] > army_scores[1]:
            return [GameOutcome.VICTORY, GameOutcome.DEFEAT]
        elif army_scores[0] < army_scores[1]:
            return [GameOutcome.DEFEAT, GameOutcome.VICTORY]
        else:
            return [GameOutcome.DRAW, GameOutcome.DRAW]
