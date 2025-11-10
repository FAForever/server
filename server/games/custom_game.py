import time

from server.rating import RatingType

from .game import Game
from .game_results import ArmyOutcome
from .typedefs import GameType, InitMode, ValidityState


class CustomGame(Game):
    init_mode = InitMode.NORMAL_LOBBY
    game_type = GameType.CUSTOM

    def __init__(self, id, *args, **kwargs):
        new_kwargs = {
            "rating_type": RatingType.GLOBAL,
            "setup_timeout": 30
        }
        new_kwargs.update(kwargs)
        super().__init__(id, *args, **new_kwargs)

    async def _run_pre_rate_validity_checks(self, team_army_outcomes: list[set[ArmyOutcome]]):
        assert self.launched_at is not None

        # if there were connection issues, they are likely to show up early in
        # the match and manifest as players quitting out - in these cases, we
        # grant a grace period to custom games before we count them as ranked
        limit = len(self.players) * 60
        duration = time.time() - self.launched_at

        # As we only get extremely limited data (the army results), our lens of
        # what can look like "quitting out" is rather large (i.e. the player is
        # "defeated").
        # In other words, only if a team unanimously recalled would we know
        # there weren't any connection issues.
        looks_like_quitting = {ArmyOutcome.DEFEAT, ArmyOutcome.UNKNOWN, ArmyOutcome.CONFLICTING}
        all_outcomes = {outcome for team in team_army_outcomes for outcome in team}
        possible_conn_issues = len(all_outcomes & looks_like_quitting) > 0

        if not self.enforce_rating and possible_conn_issues and duration < limit:
            await self.mark_invalid(ValidityState.TOO_SHORT)
