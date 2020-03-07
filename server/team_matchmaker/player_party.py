from typing import List

from server.players import Player
from server.team_matchmaker.party_member import PartyMember


class PlayerParty:
    def __init__(self, owner: Player):
        self._members = [PartyMember(owner, False)]
        self.owner = owner

    @property
    def members(self):
        return frozenset(self._members)

    @property
    def is_ready(self):
        return all(member.ready for member in self._members)

    def get_member_by_player(self, player: Player):
        return next(member for member in self._members if member.player == player)

    async def add_player(self, player: Player):
        if not any([player == m.player for m in self._members]):
            self._members.append(PartyMember(player, False))

        await self.broadcast_party()

    async def remove_player(self, player: Player):
        self._members = list(filter(lambda m: m.player != player, self._members))

        await self.broadcast_party()
        await self.send_party(player)

    async def ready_player(self, player: Player):
        for member in [m for m in self._members if m.player == player]:
            member.ready = True

        await self.broadcast_party()

    async def unready_player(self, player: Player):
        for member in [m for m in self._members if m.player == player]:
            member.ready = False

        await self.broadcast_party()

    async def set_factions(self, player: Player, factions: List[bool]):
        for member in [m for m in self._members if m.player == player]:
            member.factions = factions

        await self.broadcast_party()

    async def broadcast_party(self):
        for member in self.members:
            await self.send_party(member.player)

    async def send_party(self, player: Player):
        await player.send_message({
            "command": "update_party",
            "owner": self.owner.id,
            "members": [m.serialize() for m in self._members]
        })

    def is_disbanded(self) -> bool:
        return not any([m.player == self.owner for m in self._members])

    async def disband(self):
        members = self.members

        self._members = set()

        for member in members:
            await self.send_party(member.player)
