from server.players import Player


class PartyMember:
    def __init__(self, player: Player, ready: bool = False):
        self.player = player
        self.ready = ready
        self.factions = [True, True, True, True]

    def to_dict(self):
        return {
            "player": self.player.id,
            "ready": self.ready,
            "factions": self.factions
        }
