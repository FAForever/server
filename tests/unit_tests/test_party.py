from server.factions import Faction
from server.team_matchmaker import PartyMember


def test_member_set_faction(player_factory):
    player = player_factory("Test", with_lobby_connection=False)

    member = PartyMember(player)

    member.factions = [True, False, False, False]
    member.set_player_faction()
    assert player.faction == Faction.uef

    member.factions = [False, True, False, False]
    member.set_player_faction()
    assert player.faction == Faction.aeon

    member.factions = [False, False, True, False]
    member.set_player_faction()
    assert player.faction == Faction.cybran

    member.factions = [False, False, False, True]
    member.set_player_faction()
    assert player.faction == Faction.seraphim
