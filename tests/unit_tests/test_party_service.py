import pytest
from asynctest import CoroutineMock
from pytest import fixture
from server.exceptions import ClientError
from server.party_service import PartyService
from server.team_matchmaker import PlayerParty

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


@fixture
def party_service(game_service):
    return PartyService(game_service)


def get_members(party: PlayerParty):
    return set(pm.player for pm in party.members)


async def test_invite_player_to_party(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)


async def test_invite_foe_to_party(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)
    receiver.foes = {1}

    with pytest.raises(ClientError):
        await party_service.invite_player_to_party(sender, receiver)


async def test_accept_invite(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
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

    await party_service.invite_player_to_party(sender1, receiver)
    await party_service.invite_player_to_party(sender2, receiver)
    await party_service.accept_invite(receiver, sender1)

    with pytest.raises(ClientError):
        await party_service.accept_invite(receiver, sender2)


async def test_invite_player_to_party_not_owner(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
    await party_service.accept_invite(receiver, sender)

    with pytest.raises(ClientError):
        await party_service.invite_player_to_party(receiver, sender)


async def test_kick_player(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
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

    await party_service.invite_player_to_party(sender, receiver)

    with pytest.raises(ClientError):
        await party_service.kick_player_from_party(sender, receiver)


async def test_kick_player_not_owner(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
    await party_service.accept_invite(receiver, sender)

    with pytest.raises(ClientError):
        await party_service.kick_player_from_party(receiver, sender)


async def test_leave_party(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
    await party_service.leave_party(sender)

    assert sender not in party_service.player_parties


async def test_leave_party_twice(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
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

    await party_service.invite_player_to_party(owner, player2)
    await party_service.accept_invite(player2, owner)

    # The player who was invited leaves
    await party_service.leave_party(player2)

    assert owner in party_service.player_parties
    assert get_members(party_service.player_parties[owner]) == {owner}
    assert player2 not in party_service.player_parties


async def test_leave_party_owner_causes_disband(party_service, player_factory):
    owner = player_factory(player_id=1)
    player2 = player_factory(player_id=2)

    await party_service.invite_player_to_party(owner, player2)
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
    await party_service.invite_player_to_party(player1, player2)
    await party_service.accept_invite(player2, player1)

    # Both players leave the party
    await party_service.leave_party(player2)
    await party_service.leave_party(player1)

    # One of the players tries to create another party
    await party_service.invite_player_to_party(player1, player3)


async def test_ready_player(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)

    assert not party_service.player_parties[sender].is_ready
    await party_service.ready_player(sender)
    assert party_service.player_parties[sender].is_ready


async def test_ready_player_twice(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)
    sender.send_message = CoroutineMock()

    await party_service.invite_player_to_party(sender, receiver)

    assert not party_service.player_parties[sender].is_ready
    await party_service.ready_player(sender)
    assert party_service.player_parties[sender].is_ready
    sender.send_message.assert_called_once()

    await party_service.ready_player(sender)
    sender.send_message.call_count == 2


async def test_ready_player_nonexistent(party_service, player_factory):
    player = player_factory(player_id=1)

    with pytest.raises(ClientError):
        await party_service.ready_player(player)


async def test_unready_player(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
    await party_service.ready_player(sender)

    assert party_service.player_parties[sender].is_ready
    await party_service.unready_player(sender)
    assert not party_service.player_parties[sender].is_ready


async def test_unready_player_twice(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)
    sender.send_message = CoroutineMock()

    await party_service.invite_player_to_party(sender, receiver)
    await party_service.ready_player(sender)

    assert party_service.player_parties[sender].is_ready
    await party_service.unready_player(sender)
    assert not party_service.player_parties[sender].is_ready
    assert sender.send_message.call_count == 2

    await party_service.unready_player(sender)
    assert sender.send_message.call_count == 3


async def test_unready_player_nonexistent(party_service, player_factory):
    player = player_factory(player_id=1)

    with pytest.raises(ClientError):
        await party_service.unready_player(player)


async def test_player_disconnected(party_service, player_factory):
    sender = player_factory(player_id=1)
    receiver = player_factory(player_id=2)

    await party_service.invite_player_to_party(sender, receiver)
    await party_service.on_player_disconnected(sender)

    assert sender not in party_service.player_parties


async def test_remove_disbanded_parties(party_service, player_factory):
    """ Artificially construct some inconsistent state and verify that
        `remove_disbanded_parties` cleans it up correctly """

    player = player_factory(player_id=1)
    player2 = player_factory(player_id=2)

    party = PlayerParty(player)

    disbanded_party = PlayerParty(player2)
    await disbanded_party.disband()

    party_service.player_parties = {
        player: party,
        player2: disbanded_party
    }
    await party_service.invite_player_to_party(player2, player)

    await party_service.remove_disbanded_parties()

    assert party_service.player_parties == {
        player: party
    }

    with pytest.raises(ClientError):
        await party_service.accept_invite(player, player2)
