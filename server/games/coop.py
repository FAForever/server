from server.abc.base_game import InitMode

from .game import Game, ValidityState, Victory


class CoopGame(Game):
    """Class for coop game"""
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, *args, **kwargs):
        kwargs["game_mode"] = 'coop'
        super().__init__(*args, **kwargs)

        self.validity = ValidityState.COOP_NOT_RANKED
        self.gameOptions.update({
            'Victory': Victory.SANDBOX,
            'TeamSpawn': 'fixed',
            'RevealedCivilians': 'No',
            'Difficulty': 3,
            'Expansion': 'true'
        })
