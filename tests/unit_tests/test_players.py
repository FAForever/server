from trueskill import Rating
from src.abc.faction import Faction
from src.players import Player


def test_ratings():
    p = Player('Schroedinger')
    p.global_rating = (1500, 20)
    assert p.global_rating == Rating(1500, 20)
    p.global_rating = Rating(1700, 20)
    assert p.global_rating == Rating(1700, 20)
    p.ladder_rating = (1200, 20)
    assert p.ladder_rating == Rating(1200, 20)


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

