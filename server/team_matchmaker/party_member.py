import random

from server.players import Player

from ..factions import Faction


class PartyMember:
    def __init__(self, player: Player, ready: bool = False):
        self.player = player
        self.ready = ready
        self.factions = [True, True, True, True]

    def set_player_faction(self) -> None:
        assert any(self.factions), "At least one faction must be allowed!"

        selected = [
            Faction(i + 1) for i in range(len(self.factions))
            if self.factions[i]
        ]
        self.player.faction = random.choice(selected)

    def to_dict(self):
        return {
            "player": self.player.id,
            "ready": self.ready,
            "factions": self.factions
        }
