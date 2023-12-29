from server.games.validator import COMMON_RULES, GameOptionRule, Validator

from .game import Game
from .typedefs import FA, GameType, InitMode, ValidityState, Victory


class CoopGame(Game):
    """Class for coop game"""
    init_mode = InitMode.NORMAL_LOBBY
    game_type = GameType.COOP
    default_validity = ValidityState.COOP_NOT_RANKED
    validator = Validator([
        *COMMON_RULES,
        GameOptionRule("Victory", Victory.SANDBOX, ValidityState.WRONG_VICTORY_CONDITION),
        GameOptionRule("TeamSpawn", "fixed", ValidityState.SPAWN_NOT_FIXED),
        GameOptionRule("RevealedCivilians", FA.DISABLED, ValidityState.CIVILIANS_REVEALED),
        GameOptionRule("Difficulty", 3, ValidityState.WRONG_DIFFICULTY),
        GameOptionRule("Expansion", FA.ENABLED, ValidityState.EXPANSION_DISABLED),
    ])

    def __init__(self, *args, **kwargs):
        kwargs["game_mode"] = "coop"
        super().__init__(*args, **kwargs)

        self.is_coop = True
        self.game_options.update({
            "Victory": Victory.SANDBOX,
            "TeamSpawn": "fixed",
            "RevealedCivilians": "No",
            "Difficulty": 3,
            "Expansion": "true"
        })
        self.leaderboard_saved = False

    async def process_game_results(self):
        """
        When a coop game ends, we don't expect there to be any game results.
        """
        pass
