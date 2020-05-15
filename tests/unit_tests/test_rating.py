import pytest

from server.rating import PlayerRatings, RatingType


@pytest.fixture
def ratings():
    PlayerRatings.clear()
    return PlayerRatings(default=(1500, 500))


@pytest.fixture(scope="session")
def persistent_ratings():
    return PlayerRatings(default=(1500, 500))


def test_rating_type_default(ratings):
    for rating_type in RatingType:
        assert ratings[rating_type] == (1500, 500)


def test_rating_type_invalid(ratings):
    for key in ("invalid", 0):
        with pytest.raises(KeyError):
            ratings[key]


@pytest.mark.asyncio
async def test_int_keys(persistent_ratings, rating_service):
    for key in (1, 2, 3, "global", "ladder_1v1", "tmm_2v2"):
        assert persistent_ratings[key] == (1500, 500)
