import pytest

from server.rating import PlayerRatings, RatingType


@pytest.fixture
def ratings():
    return PlayerRatings(lambda: (1500, 500))


def test_leaderboard_class():
    global_l = Leaderboard(1, "global", None)
    assert global_l == Leaderboard(1, "global", None)
    assert global_l != Leaderboard(2, "ladder1v1", global_l)
    assert global_l != Leaderboard(1, "global", global_l)


def test_rating_type_default(ratings):
    for rating_type in (RatingType.GLOBAL, RatingType.LADDER_1V1):
        assert ratings[rating_type] == (1500, 500)


def test_str_keys(ratings):
    ratings["global"] = (1000, 10)

    assert ratings[RatingType.GLOBAL] == ratings["global"] == (1000, 10)


def test_key_type(ratings):
    ratings[RatingType.GLOBAL]
    ratings[RatingType.LADDER_1V1]

    assert ratings == {"global": (1500, 500), "ladder_1v1": (1500, 500)}
    assert list(ratings) == ["global", "ladder_1v1"]
