from unittest.mock import Mock

import pytest
from asynctest import CoroutineMock

from server.exceptions import ClientError
from server.factions import Faction
from server.party_service import PartyService
from server.team_matchmaker import PlayerParty

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def party_service(game_service):
    service = PartyService(game_service)
    await service.initialize()
    yield service
    await service.shutdown()


@pytest.fixture
def player_factory(player_factory):
    def make(*args, **kwargs):
        passed_kwargs = dict(with_lobby_connection=False)
        passed_kwargs.update(kwargs)
        player = player_factory(*args, **passed_kwargs)
        player.send_message = CoroutineMock()
        player.write_message = Mock()
        return player

    return make


def get_members(party: PlayerParty):
    return set(member.player for member in party)


async def test_get_party(party_service, player_factory):
    player = player_factory(player_id=1)
    party = party_service.get_party(player)

    assert party
    assert party_service.player_parties[player] is party
    assert party.owner is player


async def test_invite_player_to_party(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    assert party_service.player_parties[sender]


async def test_accept_invite(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    assert get_members(party_service.player_parties[sender]) == {sender}

    await party_service.accept_invite(receiver, sender)
    assert get_members(party_service.player_parties[sender]) == {
        sender,
        receiver
    }


async def test_accept_invite_nonexistent(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    with pytest.raises(ClientError):
        await party_service.accept_invite(receiver, sender)


async def test_accept_invite_two_invites(party_service, player_factory):
    sender1 = player_factory(player_id=1)
    sender2 = player_factory(player_id=2)
    receiver = player_factory(player_id=3)

    party_service.invite_player_to_party(sender1, receiver)
    party_service.invite_player_to_party(sender2, receiver)
    await party_service.accept_invite(receiver, sender1)

    await party_service.accept_invite(receiver, sender2)

    assert receiver in party_service.player_parties
    assert sender2 in party_service.player_parties[receiver]
    assert sender1 not in party_service.player_parties[receiver]


async def test_invite_player_to_party_not_owner(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    await party_service.accept_invite(receiver, sender)

    with pytest.raises(ClientError):
        party_service.invite_player_to_party(receiver, sender)


async def test_kick_player(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    await party_service.accept_invite(receiver, sender)

    assert get_members(party_service.player_parties[sender]) == {
        sender,
        receiver
    }
    await party_service.kick_player_from_party(sender, receiver)
    assert get_members(party_service.player_parties[sender]) == {sender}


async def test_kick_player_nonexistent(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    with pytest.raises(ClientError):
        await party_service.kick_player_from_party(sender, receiver)


async def test_kick_player_not_in_party(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)

    await party_service.kick_player_from_party(sender, receiver)
    sender.send_message.assert_called_once()


async def test_kick_player_not_owner(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    await party_service.accept_invite(receiver, sender)

    with pytest.raises(ClientError):
        await party_service.kick_player_from_party(receiver, sender)


async def test_leave_party(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    await party_service.leave_party(sender)

    assert sender not in party_service.player_parties


async def test_leave_party_twice(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    await party_service.leave_party(sender)

    assert sender not in party_service.player_parties

    with pytest.raises(ClientError):
        await party_service.leave_party(sender)


async def test_leave_party_nonexistent(party_service, player_factory):
    player = player_factory(player_id=1)

    with pytest.raises(ClientError):
        await party_service.leave_party(player)


async def test_leave_party_not_owner(party_service, player_factory):
    owner = player_factory(player_id=1)
    player2 = player_factory(player_id=2)

    party_service.invite_player_to_party(owner, player2)
    await party_service.accept_invite(player2, owner)

    # The player who was invited leaves
    await party_service.leave_party(player2)

    assert owner in party_service.player_parties
    assert get_members(party_service.player_parties[owner]) == {owner}
    assert player2 not in party_service.player_parties


async def test_leave_party_owner_causes_disband(party_service, player_factory):
    owner = player_factory(player_id=1)
    player2 = player_factory(player_id=2)

    party_service.invite_player_to_party(owner, player2)
    await party_service.accept_invite(player2, owner)

    # Owner leaves
    await party_service.leave_party(owner)

    assert owner not in party_service.player_parties
    assert player2 not in party_service.player_parties


async def test_leave_party_then_join_another(party_service, player_factory):
    player1 = player_factory(player_id=1)
    player2 = player_factory(player_id=2)
    player3 = player_factory(player_id=3)

    # Join 2 players into a party
    party_service.invite_player_to_party(player1, player2)
    await party_service.accept_invite(player2, player1)

    # Both players leave the party
    await party_service.leave_party(player2)
    await party_service.leave_party(player1)

    # One of the players tries to create another party
    party_service.invite_player_to_party(player1, player3)


async def test_set_factions(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    # Create a party
    party_service.invite_player_to_party(sender, receiver)

    party_service.set_factions(sender, [1, 4])

    party_member = next(iter(party_service.player_parties[sender].members))
    assert party_member.factions == [Faction.uef, Faction.seraphim]


async def test_set_factions_creates_party(party_service, player_factory):
    # TODO: Is this really the behavior we want?
    player = player_factory(player_id=1)

    party_service.set_factions(player, [1, 3])
    assert player in party_service.player_parties


async def test_player_disconnected(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    party_service.invite_player_to_party(sender, receiver)
    await party_service.on_player_disconnected(sender)

    assert sender not in party_service.player_parties
