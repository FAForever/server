from server.abc.base_game import InitMode

from .game import Game, ValidityState


class CoopGame(Game):
    """Class for coop game"""
    init_mode = InitMode.NORMAL_LOBBY

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.validity = ValidityState.COOP_NOT_RANKED
