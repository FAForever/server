import time
from typing import Dict, List, NamedTuple, Optional, Tuple

from .decorators import with_logger
from .exceptions import ClientError
from .game_service import GameService
from .players import Player
from .team_matchmaker.player_party import PlayerParty


class GroupInvite(NamedTuple):
    sender: Player
    recipient: Player
    party: PlayerParty
    created_at: float


PARTY_INVITE_TIMEOUT = 60 * 60 * 24  # secs


@with_logger
class PartyService:
    """
    Service responsible for managing the global team matchmaking. Does grouping,
    matchmaking, updates statistics, and launches the games.
    """

    def __init__(self, game_service: GameService):
        self.game_service = game_service
        self.player_parties: Dict[Player, PlayerParty] = dict()
        self._pending_invites: Dict[Tuple[Player, Player], GroupInvite] = dict()

    def get_party(self, owner: Player) -> Optional[PlayerParty]:
        return self.player_parties.get(owner)

    def invite_player_to_party(self, sender: Player, recipient: Player):
        """
        Creates a new party for `sender` if one doesn't exist, and invites
        `recipient` to that party.
        """
        if sender not in self.player_parties:
            self.player_parties[sender] = PlayerParty(sender)

        party = self.player_parties[sender]

        if party.owner != sender:
            raise ClientError("You do not own this party.", recoverable=True)

        self._pending_invites[(sender, recipient)] = GroupInvite(
            sender, recipient, party, time.time()
        )
        recipient.write_message({
            "command": "party_invite",
            "sender": sender.id
        })

    async def accept_invite(self, recipient: Player, sender: Player):
        if (sender, recipient) not in self._pending_invites:
            raise ClientError("You are not invited to that party (anymore)", recoverable=True)

        if recipient in self.player_parties:
            await self.leave_party(recipient)

        party = self._pending_invites.pop((sender, recipient)).party

        # TODO: Is it possible for this to fail?
        assert party == self.player_parties.get(sender)
        if party != self.player_parties.get(sender):
            await recipient.send_message({'command': 'party_disbanded'})
            return

        party.add_player(recipient)
        self.player_parties[recipient] = party
        party.write_broadcast_party()

    async def kick_player_from_party(self, owner: Player, kicked_player: Player):
        if owner not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        if kicked_player not in self.player_parties:
            raise ClientError("That player is not in a party.", recoverable=True)

        party = self.player_parties[owner]

        if party.owner != owner:
            raise ClientError("You do not own that party.", recoverable=True)

        if kicked_player not in party:
            # Client state appears to be out of date
            await party.send_party(owner)
            return

        party.remove_player(kicked_player)
        party.write_broadcast_party()
        del self.player_parties[kicked_player]

        # TODO: Pick one of these
        await party.send_party(kicked_player)
        kicked_player.write_message({"command": "kicked_from_party"})

    async def leave_party(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[player]
        party.remove_player(player)
        party.write_broadcast_party()
        await party.send_party(player)

        del self.player_parties[player]
        await self.remove_disbanded_parties()

    async def ready_player(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[player]

        if party.get_member_by_player(player).ready:
            # Client state appears to be out of date
            await party.send_party(player)
            return

        party.ready_player(player)
        party.write_broadcast_party()

    async def unready_player(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[player]

        if not party.get_member_by_player(player).ready:
            # Client state appears to be out of date
            await party.send_party(player)
            return

        party.unready_player(player)
        party.write_broadcast_party()

    async def set_factions(self, player: Player, factions: List[bool]):
        if player not in self.player_parties:
            self.player_parties[player] = PlayerParty(player)
            # raise ClientError("You are not in a party.", recoverable=True) TODO can we just create a party here?

        party = self.player_parties[player]
        party.set_factions(player, factions)
        party.write_broadcast_party()

    def clear_invites(self):
        invites = filter(
            lambda inv: time.time() - inv.created_at >= PARTY_INVITE_TIMEOUT or
            inv.sender not in self.player_parties,
            self._pending_invites.values()
        )

        for invite in list(invites):
            del self._pending_invites[(invite.sender, invite.recipient)]

    async def remove_party(self, party):
        # Remove all players who were in the party
        party_members = map(
            lambda i: i[0],
            filter(
                lambda i: party == i[1],
                self.player_parties.items()
            )
        )
        for player in list(party_members):
            del self.player_parties[player]

        # Remove all invites to the party
        invites = filter(
            lambda inv: inv.party == party,
            self._pending_invites.values()
        )
        for invite in list(invites):
            del self._pending_invites[(invite.sender, invite.recipient)]

        members = party.members
        party.disband()
        # TODO: Send a special "disbanded" command?
        party.write_broadcast_party(players=members)

    async def remove_disbanded_parties(self):
        disbanded_parties = filter(
            lambda party: party.is_disbanded(),
            self.player_parties.values()
        )

        for party in list(disbanded_parties):
            # This will call disband again therefore removing all players and informing them
            await self.remove_party(party)

        self.clear_invites()

    async def on_player_disconnected(self, player):
        if player in self.player_parties:
            await self.leave_party(player)
