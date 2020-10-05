import pytest

from server.team_matchmaker import PartyMember, PlayerParty


@pytest.fixture
def party(players):
    party = PlayerParty(players.hosting)
    party.add_player(players.joining)
    party.add_invited_player(players.peer)
    return party


def test_basic(party, players):
    assert not party.is_disbanded()
    assert players.hosting in party
    assert players.joining in party
    assert list(party) == [
        party.get_member_by_player(players.hosting),
        party.get_member_by_player(players.joining)
    ]
    assert party.players == [players.hosting, players.joining]


def test_add_players(party, player_factory):
    player1 = player_factory("Test1")
    player2 = player_factory("Test2")

    member2 = PartyMember(player2)

    party.add_player(player1)
    assert player1 in party

    party.add_member(member2)
    assert player2 in party
    assert member2 in party.members
    assert party.get_member_by_player(player2) is member2


def test_remove_players(party, players):
    party.remove_player(players.hosting)
    assert players.hosting not in party
    assert party.get_member_by_player(players.hosting) is None
    assert party.players == [players.joining]
    assert party.members == {party.get_member_by_player(players.joining)}


def test_invite_players(party, players, player_factory):
    player1 = player_factory("Test1")

    party.add_invited_player(player1)
    assert player1 in party.invited_players
    assert not party.invited_players[player1].is_expired()

    party.remove_invited_player(player1)
    assert player1 not in party.invited_players

    party.add_invited_player(player1)
    assert player1 in party.invited_players

    # When the party owner leaves, their invites should be cleared
    party.remove_player(players.hosting)
    assert party.invited_players == {}


def test_clear(party, players):
    party.clear()
    assert party.players == []
    assert party.members == set()
    assert party.invited_players == {}
    assert players.hosting not in party
    assert players.joining not in party


def test_serialize(party, players):
    assert party.to_dict() == {
        "owner": players.hosting.id,
        "members": [
            {
                "player": players.hosting.id,
                "factions": ["uef", "aeon", "cybran", "seraphim"]
            },
            {
                "player": players.joining.id,
                "factions": ["uef", "aeon", "cybran", "seraphim"]
            }
        ]
    }
