import time
from typing import List, NamedTuple, Optional

from .decorators import with_logger
from .exceptions import ClientError
from .game_service import GameService
from .players import Player
from .team_matchmaker.player_party import PlayerParty

GroupInvite = NamedTuple('GroupInvite', [("sender", Player), ("recipient", Player), ("party", PlayerParty), ("created_at", float)])

PARTY_INVITE_TIMEOUT = 60 * 60 * 24  # secs


@with_logger
class PartyService:
    """
    Service responsible for managing the global team matchmaking. Does grouping, matchmaking, updates statistics, and
    launches the games.
    """

    def __init__(self, games_service: GameService):
        self.game_service = games_service
        self.player_parties: dict[Player, PlayerParty] = dict()
        self._pending_invites: dict[(Player, Player), GroupInvite] = dict()

    def get_party(self, owner: Player) -> Optional[PlayerParty]:
        return self.player_parties.get(owner)

    async def invite_player_to_party(self, sender: Player, recipient: Player):
        if sender not in self.player_parties:
            self.player_parties[sender] = PlayerParty(sender)

        party = self.player_parties[sender]

        if party.owner != sender:
            raise ClientError("You do not own this party.", recoverable=True)

        if sender.id in recipient.foes:
            # TODO: Make this a separate command so it can be locallized correctly
            raise ClientError("This person does not accept invites from you.", recoverable=True)

        self._pending_invites[(sender, recipient)] = GroupInvite(sender, recipient, party, time.time())
        await recipient.send_message({
            "command": "party_invite",
            "sender": sender.id
        })

    async def accept_invite(self, recipient: Player, sender: Player):
        if (sender, recipient) not in self._pending_invites:
            raise ClientError("You are not invited to a party (anymore)", recoverable=True)

        if recipient in self.player_parties:
            raise ClientError("You are already in a party.", recoverable=True)

        pending_invite = self._pending_invites.pop((sender, recipient))

        if pending_invite.party != self.player_parties.get(sender):
            await recipient.send_message({'command': 'party_disbanded'})
            return

        self.player_parties[recipient] = pending_invite.party
        await pending_invite.party.add_player(recipient)

        await self.remove_disbanded_parties()

    async def kick_player_from_party(self, owner: Player, kicked_player: Player):
        if owner not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        if kicked_player not in self.player_parties:
            raise ClientError("That player is not in a party.", recoverable=True)

        party = self.player_parties[owner]

        if party.owner != owner:
            raise ClientError("You do not own that party.", recoverable=True)

        if not any([m.player == kicked_player] for m in party.members):
            # Ensure client state is up to date
            await party.send_party(owner)
            return

        await party.remove_player(kicked_player)
        self.player_parties.pop(kicked_player)
        await kicked_player.send_message({"command": "kicked_from_party"})

    async def leave_party(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        await self.player_parties[player].remove_player(player)
        self.player_parties.pop(player)

        await self.remove_disbanded_parties()

    async def ready_player(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[player]

        if party.get_member_by_player(player).ready:
            # Ensure client state is up to date
            await party.send_party(player)
            return

        await party.ready_player(player)

    async def unready_player(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[player]

        if not party.get_member_by_player(player).ready:
            # Ensure client state is up to date
            await party.send_party(player)
            return

        await party.unready_player(player)

    def set_factions(self, player: Player, factions: List[bool]):
        if player not in self.player_parties:
            self.player_parties[player] = PlayerParty(player)
            # raise ClientError("You are not in a party.", recoverable=True) TODO can we just create a party here?

        party = self.player_parties[player]
        party.set_factions(player, factions)

    def clear_invites(self):
        invites = filter(
            lambda inv: time.time() - inv.created_at >= PARTY_INVITE_TIMEOUT or
            inv.sender not in self.player_parties,
            self._pending_invites.values()
        )

        for invite in list(invites):
            self._pending_invites.pop((invite.sender, invite.recipient))

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
            self.player_parties.pop(player)

        # Remove all invites to the party
        invites = filter(
            lambda inv: inv.party == party,
            self._pending_invites.values()
        )
        for invite in list(invites):
            self._pending_invites.pop((invite.sender, invite.recipient))

        await party.disband()

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
