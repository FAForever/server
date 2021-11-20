from .game import Game
from .typedefs import FA, GameType, ValidityState, Victory


class CoopGame(Game):
    """Class for coop game"""
    game_type = GameType.COOP

    def __init__(self, *args, **kwargs):
        kwargs["game_mode"] = "coop"
        super().__init__(*args, **kwargs)

        self.validity = ValidityState.COOP_NOT_RANKED
        self.gameOptions.update({
            "Victory": Victory.SANDBOX,
            "TeamSpawn": "fixed",
            "RevealedCivilians": "No",
            "Difficulty": 3,
            "Expansion": "true"
        })
        self.leaderboard_saved = False

    async def validate_game_mode_settings(self):
        """
        Checks which only apply to the coop mode
        """

        valid_options = {
            "Victory": (Victory.SANDBOX, ValidityState.WRONG_VICTORY_CONDITION),
            "TeamSpawn": ("fixed", ValidityState.SPAWN_NOT_FIXED),
            "RevealedCivilians": (FA.DISABLED, ValidityState.CIVILIANS_REVEALED),
            "Difficulty": (3, ValidityState.WRONG_DIFFICULTY),
            "Expansion": (FA.ENABLED, ValidityState.EXPANSION_DISABLED),
        }
        await self._validate_game_options(valid_options)

    async def process_game_results(self):
        """
        When a coop game ends, we don't expect there to be any game results.
        """
        pass
