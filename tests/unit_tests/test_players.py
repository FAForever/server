import gc
from unittest import mock

import pytest

from server.factions import Faction
from server.players import Player
from server.protocol import DisconnectedError
from server.rating import RatingType
from trueskill import Rating


def test_ratings():
    p = Player('Schroedinger')
    p.ratings[RatingType.GLOBAL] = (1500, 20)
    assert p.ratings[RatingType.GLOBAL] == (1500, 20)
    p.ratings[RatingType.GLOBAL] = Rating(1700, 20)
    assert p.ratings[RatingType.GLOBAL] == (1700, 20)
    p.ratings[RatingType.LADDER_1V1] = (1200, 20)
    assert p.ratings[RatingType.LADDER_1V1] == (1200, 20)
    p.ratings[RatingType.LADDER_1V1] = Rating(1200, 20)
    assert p.ratings[RatingType.LADDER_1V1] == (1200, 20)


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
               ratings={
                   RatingType.GLOBAL: (1234, 68),
                   RatingType.LADDER_1V1: (1500, 230),
               },
               clan='TOAST',
               game_count={RatingType.GLOBAL: 542})
    assert p.to_dict() == {
                    "id": 42,
                    "login": 'Something',
                    "global_rating": (1234, 68),
                    "ladder_rating": (1500, 230),
                    "number_of_games": 542,
                    "clan": 'TOAST'
    }


@pytest.mark.asyncio
async def test_send_message():
    p = Player(login='Test')

    assert p.lobby_connection is None
    with pytest.raises(DisconnectedError):
        await p.send_message({})
