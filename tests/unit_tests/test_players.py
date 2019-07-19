import gc
from unittest import mock

from server.factions import Faction
from server.players import Player
from trueskill import Rating


def test_ratings():
    p = Player('Schroedinger')
    p.global_rating = (1500, 20)
    assert p.global_rating == (1500, 20)
    p.global_rating = Rating(1700, 20)
    assert p.global_rating == (1700, 20)
    p.ladder_rating = (1200, 20)
    assert p.ladder_rating == (1200, 20)
    p.ladder_rating = Rating(1200, 20)
    assert p.ladder_rating == (1200, 20)


def test_faction():
    """
    Yes, this test was motivated by a bug
    :return:
    """
    p = Player('Schroedinger2')
    p.faction = 'aeon'
    assert p.faction == Faction.aeon
    p.faction = Faction.aeon
    assert p.faction == Faction.aeon


def test_equality_by_id():
    p = Player('Sheeo', 42)
    p2 = Player('RandomSheeo', 42)
    assert p == p2
    assert p.__hash__() == p2.__hash__()


def test_weak_references():
    p = Player(login='Test')
    weak_properties = ['lobby_connection', 'game']
    referent = mock.Mock()
    for prop in weak_properties:
        setattr(p, prop, referent)

    del referent
    gc.collect()

    for prop in weak_properties:
        assert getattr(p, prop) is None

def test_unlink_weakref():
    p = Player(login='Test')
    mock_game = mock.Mock()
    p.game = mock_game
    assert p.game == mock_game
    del p.game
    assert p.game is None

def test_serialize():
    p = Player(player_id=42,
               login='Something',
               global_rating=(1234, 68),
               ladder_rating=(1500, 230),
               clan='TOAST',
               num_games=542)
    assert p.to_dict() == {
                    "id": 42,
                    "login": 'Something',
                    "global_rating": (1234, 68),
                    "ladder_rating": (1500, 230),
                    "number_of_games": 542,
                    "clan": 'TOAST'
    }
