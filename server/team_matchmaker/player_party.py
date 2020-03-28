from typing import List

from server.players import Player
from server.team_matchmaker.party_member import PartyMember


class PlayerParty:
    def __init__(self, owner: Player):
        self._members = {
            owner: PartyMember(owner)
        }
        self.owner = owner

    def __contains__(self, player: Player) -> bool:
        return player in self._members

    @property
    def members(self):
        return frozenset(self._members.values())

    def is_ready(self) -> bool:
        return all(member.ready for member in self._members.values())

    def is_disbanded(self) -> bool:
        return not any(m.player == self.owner for m in self._members.values())

    def get_member_by_player(self, player: Player):
        return self._members.get(player)

    def add_player(self, player: Player):
        self._members[player] = PartyMember(player)

    def remove_player(self, player: Player):
        del self._members[player]

    def ready_player(self, player: Player):
        self._members[player].ready = True

    def unready_player(self, player: Player):
        self._members[player].ready = False

    def set_factions(self, player: Player, factions: List[bool]):
        self._members[player].factions = factions

    def write_broadcast_party(self, players=None):
        """
        Send a party update to all players in the party
        """
        if not players:
            players = self.members
        msg = {
            "command": "update_party",
            **self.to_dict()
        }
        for member in players:
            # Will re-encode the message for each player
            member.player.write_message(msg)

    async def send_party(self, player: Player):
        await player.send_message({
            "command": "update_party",
            **self.to_dict()
        })

    def disband(self):
        self._members.clear()

    def to_dict(self):
        return {
            "owner": self.owner.id,
            "members": [m.to_dict() for m in self._members.values()]
        }
