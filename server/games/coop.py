from server.abc.base_game import InitMode

from .game import Game, GameType, ValidityState, Victory


class CoopGame(Game):
    """Class for coop game"""
    init_mode = InitMode.NORMAL_LOBBY
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
            "Expansion": 1
        })

    async def validate_game_mode_settings(self):
        """
        Checks which only apply to the coop mode
        """

        valid_options = {
            "Victory": (Victory.SANDBOX, ValidityState.WRONG_VICTORY_CONDITION),
            "TeamSpawn": ("fixed", ValidityState.SPAWN_NOT_FIXED),
            "RevealedCivilians": ("No", ValidityState.CIVILIANS_REVEALED),
            "Difficulty": (3, ValidityState.WRONG_DIFFICULTY),
            "Expansion": (1, ValidityState.EXPANSION_DISABLED),
        }
        await self._validate_game_options(valid_options)
