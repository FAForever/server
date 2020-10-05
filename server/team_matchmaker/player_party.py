import time
from typing import FrozenSet, List, NamedTuple, Optional

from server.factions import Faction
from server.players import Player
from server.team_matchmaker.party_member import PartyMember

PARTY_INVITE_TIMEOUT = 60 * 60 * 24  # secs


class GroupInvite(NamedTuple):
    recipient: Player
    created_at: float

    def is_expired(self) -> bool:
        return time.time() - self.created_at >= PARTY_INVITE_TIMEOUT


class PlayerParty():
    def __init__(self, owner: Player):
        self._members = {
            owner: PartyMember(owner)
        }
        self.invited_players = {}
        self.owner = owner

    def __contains__(self, player: Player) -> bool:
        return player in self._members

    def __iter__(self):
        return iter(self._members.values())

    @property
    def members(self) -> FrozenSet[PartyMember]:
        return frozenset(self._members.values())

    @property
    def players(self) -> List[Player]:
        return list(member.player for member in self._members.values())

    def is_disbanded(self) -> bool:
        return not any(m.player == self.owner for m in self._members.values())

    def get_member_by_player(self, player: Player) -> Optional[PartyMember]:
        return self._members.get(player)

    def add_player(self, player: Player) -> None:
        self._members[player] = PartyMember(player)

    def remove_player(self, player: Player) -> None:
        assert player in self._members

        del self._members[player]
        if player == self.owner:
            self.invited_players.clear()

    def add_member(self, member: PartyMember) -> None:
        self._members[member.player] = member

    def add_invited_player(self, player: Player) -> None:
        self.invited_players[player] = GroupInvite(player, time.time())

    def remove_invited_player(self, player: Player) -> None:
        assert player in self.invited_players

        del self.invited_players[player]

    def set_factions(self, player: Player, factions: List[Faction]) -> None:
        self._members[player].factions = factions

    async def send_party(self, player: Player) -> None:
        await player.send_message({
            "command": "update_party",
            **self.to_dict()
        })

    def clear(self):
        self._members.clear()

    def to_dict(self):
        return {
            "owner": self.owner.id,
            "members": [m.to_dict() for m in self._members.values()]
        }
