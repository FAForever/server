"""
Manages interactions between players and parties
"""

from server.metrics import MonitoredDict

from .core import Service
from .decorators import with_logger
from .exceptions import ClientError
from .factions import Faction
from .game_service import GameService
from .players import Player, PlayerState
from .team_matchmaker.player_party import PlayerParty
from .timing import at_interval


@with_logger
class PartyService(Service):
    """
    Service responsible for managing the player parties.

    Logically, we consider players to always be in a party, either alone, or
    with other players.
    """

    def __init__(self, game_service: GameService):
        self.game_service = game_service
        self.player_parties: dict[Player, PlayerParty] = MonitoredDict(
            "party_service.player_parties"
        )
        self._dirty_parties: set[PlayerParty] = set()

    async def initialize(self):
        self._update_task = at_interval(1, self.update_dirties)

    async def shutdown(self):
        self._update_task.stop()

    async def update_dirties(self):
        if not self._dirty_parties:
            return

        dirty_parties = self._dirty_parties
        self._dirty_parties = set()

        for party in dirty_parties:
            try:
                self.write_broadcast_party(party)
            except Exception:  # pragma: no cover
                self._logger.exception(
                    "Unexpected exception while sending party updates!"
                )

    def write_broadcast_party(self, party, members=None):
        """
        Send a party update to all players in the party
        """
        if not members:
            members = iter(party)
        msg = {
            "command": "update_party",
            **party.to_dict()
        }
        for member in members:
            # Will re-encode the message for each player
            member.player.write_message(msg)

    def get_party(self, owner: Player) -> PlayerParty:
        party = self.player_parties.get(owner)
        if not party:
            party = PlayerParty(owner)
            self.player_parties[owner] = party

        return party

    def mark_dirty(self, party: PlayerParty):
        self._dirty_parties.add(party)

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

        party.add_invited_player(recipient)
        recipient.write_message({
            "command": "party_invite",
            "sender": sender.id
        })

    async def accept_invite(self, recipient: Player, sender: Player):
        party = self.player_parties.get(sender)
        if (
            not party or
            recipient not in party.invited_players or
            party.invited_players[recipient].is_expired()
        ):
            # TODO: Localize with a proper message
            raise ClientError("You are not invited to that party (anymore)", recoverable=True)

        if sender.state is PlayerState.SEARCHING_LADDER:
            # TODO: Localize with a proper message
            raise ClientError("That party is already in queue", recoverable=True)

        old_party = self.player_parties.get(recipient)
        if old_party is not None:
            # Preserve state (like faction selection) from the old party
            member = old_party.get_member_by_player(recipient)
            assert member is not None

            await self.leave_party(recipient)
            party.add_member(member)
        else:
            party.add_player(recipient)

        self.player_parties[recipient] = party
        self.mark_dirty(party)

    async def kick_player_from_party(self, owner: Player, kicked_player: Player):
        if owner not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[owner]

        if party.owner != owner:
            raise ClientError("You do not own that party.", recoverable=True)

        if kicked_player not in party:
            # Client state appears to be out of date
            await party.send_party(owner)
            return

        party.remove_player(kicked_player)
        del self.player_parties[kicked_player]

        kicked_player.write_message({"command": "kicked_from_party"})

        self.mark_dirty(party)

    async def leave_party(self, player: Player):
        if player not in self.player_parties:
            raise ClientError("You are not in a party.", recoverable=True)

        party = self.player_parties[player]
        self._remove_player_from_party(player, party)
        # TODO: Remove?
        await party.send_party(player)

    def _remove_player_from_party(self, player, party):
        party.remove_player(player)
        del self.player_parties[player]

        if party.is_disbanded():
            self.remove_party(party)
            return

        self.mark_dirty(party)

    def set_factions(self, player: Player, factions: list[Faction]):
        if player not in self.player_parties:
            self.player_parties[player] = PlayerParty(player)

        party = self.player_parties[player]
        party.set_factions(player, factions)
        self.mark_dirty(party)

    def remove_party(self, party):
        # Remove all players who were in the party
        self._logger.info("Removing party: %s", party.members)
        for member in party:
            self._logger.info("Removing party for player %s", member.player)
            if party == self.player_parties.get(member.player):
                del self.player_parties[member.player]
            else:
                self._logger.warning(
                    "Player %s was in two parties at once!", member.player
                )

        members = party.members
        party.clear()
        # TODO: Send a special "disbanded" command?
        self.write_broadcast_party(party, members=members)

    def on_connection_lost(self, conn: "LobbyConnection") -> None:
        if not conn.player or conn.player not in self.player_parties:
            return

        self._remove_player_from_party(
            conn.player,
            self.player_parties[conn.player]
        )
