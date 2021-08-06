import pytest

from server.rating import Leaderboard, PlayerRatings, RatingType

DEFAULT_RATING = (1500, 500)


@pytest.fixture
def ratings():
    return PlayerRatings({})


@pytest.fixture
def cyclic_leaderboards():
    global_l = Leaderboard(1, "global")
    tmm2v2_l = Leaderboard(2, "tmm_2v2", global_l)
    global_l.initializer = tmm2v2_l
    return {
        global_l.technical_name: global_l,
        tmm2v2_l.technical_name: tmm2v2_l
    }


@pytest.fixture
def cyclic_ratings(cyclic_leaderboards):
    return PlayerRatings(cyclic_leaderboards)


@pytest.fixture
def long_cyclic_ratings():
    ladder_l = Leaderboard(3, "ladder_1v1")
    global_l = Leaderboard(1, "global", ladder_l)
    tmm2v2_l = Leaderboard(2, "tmm_2v2", global_l)
    ladder_l.initializer = tmm2v2_l
    return PlayerRatings({
        ladder_l.technical_name: ladder_l,
        global_l.technical_name: global_l,
        tmm2v2_l.technical_name: tmm2v2_l
    })


@pytest.fixture
def chained_leaderboards():
    ladder_l = Leaderboard(3, "ladder_1v1")
    global_l = Leaderboard(1, "global", ladder_l)
    tmm2v2_l = Leaderboard(2, "tmm_2v2", global_l)
    return {
        ladder_l.technical_name: ladder_l,
        global_l.technical_name: global_l,
        tmm2v2_l.technical_name: tmm2v2_l
    }


@pytest.fixture
def chained_ratings(chained_leaderboards):
    return PlayerRatings(chained_leaderboards)


def test_leaderboard_class():
    global_l = Leaderboard(1, "global", None)
    assert global_l == Leaderboard(1, "global", None)
    assert global_l != Leaderboard(2, "ladder1v1", global_l)
    assert global_l != Leaderboard(1, "global", global_l)


def test_rating_type_default(ratings):
    for rating_type in (RatingType.GLOBAL, RatingType.LADDER_1V1):
        assert ratings[rating_type] == DEFAULT_RATING


def test_rating_missing_key(ratings):
    assert ratings["Not a Rating"] == DEFAULT_RATING


def test_str_keys(ratings):
    ratings["global"] = (1000, 10)

    assert ratings[RatingType.GLOBAL] == ratings["global"] == (1000, 10)


def test_key_type(ratings):
    ratings[RatingType.GLOBAL]
    ratings[RatingType.LADDER_1V1]

    assert ratings == {"global": DEFAULT_RATING, "ladder_1v1": DEFAULT_RATING}
    assert list(ratings) == ["global", "ladder_1v1"]


def test_initialization_cycle(cyclic_ratings):
    assert cyclic_ratings["global"] == DEFAULT_RATING
    assert cyclic_ratings["tmm_2v2"] == DEFAULT_RATING


def test_long_initialization_cycle(long_cyclic_ratings):
    assert long_cyclic_ratings["ladder_1v1"] == DEFAULT_RATING
    assert long_cyclic_ratings["global"] == DEFAULT_RATING
    assert long_cyclic_ratings["tmm_2v2"] == DEFAULT_RATING


def test_initialization_cycle_with_rating(cyclic_ratings):
    cyclic_ratings["global"] = (1000, 100)
    assert cyclic_ratings["global"] == (1000, 100)
    assert cyclic_ratings["tmm_2v2"] == (1000, 250)


def test_long_initialization_cycle_with_rating(long_cyclic_ratings):
    long_cyclic_ratings["global"] = (1000, 100)
    assert long_cyclic_ratings["ladder_1v1"] == (1000, 250)
    assert long_cyclic_ratings["global"] == (1000, 100)
    assert long_cyclic_ratings["tmm_2v2"] == (1000, 250)


def test_initialization_chain(chained_ratings):
    assert chained_ratings["ladder_1v1"] == DEFAULT_RATING
    assert chained_ratings["global"] == DEFAULT_RATING
    assert chained_ratings["tmm_1v1"] == DEFAULT_RATING


def test_initialization_chain_with_rating(chained_ratings):
    chained_ratings["ladder_1v1"] = (1000, 100)
    assert chained_ratings["ladder_1v1"] == (1000, 100)
    assert chained_ratings["tmm_2v2"] == (1000, 250)


def test_initialization_transient(chained_ratings):
    chained_ratings["global"] = (1000, 100)
    assert chained_ratings["tmm_2v2"] == (1000, 250)

    chained_ratings["global"] = (700, 100)
    assert chained_ratings["tmm_2v2"] == (700, 250)

    chained_ratings["global"] = (500, 100)
    chained_ratings["tmm_2v2"] = (300, 200)
    assert chained_ratings["tmm_2v2"] == (300, 200)


def test_dict_update(chained_ratings):
    chained_ratings["ladder_1v1"] = (1000, 100)
    assert chained_ratings["global"] == (1000, 250)

    chained_ratings.update({
        "ladder_1v1": (500, 100),
        "global": (750, 100)
    })

    assert chained_ratings["ladder_1v1"] == (500, 100)
    # Global should not be re-initialized after dict update
    assert chained_ratings["global"] == (750, 100)


def test_ratings_update_same_leaderboards(chained_leaderboards):
    ratings1 = PlayerRatings(chained_leaderboards)
    ratings2 = PlayerRatings(chained_leaderboards)
    # Global is initialized based on ladder, and should be marked as transient
    ratings1["ladder_1v1"] = (1000, 100)
    assert ratings1["global"] == (1000, 250)

    ratings2.update(ratings1)
    # Existing keys should be copied
    assert ratings2 == {
        "ladder_1v1": (1000, 100),
        "global": (1000, 250)
    }
    assert ratings2["ladder_1v1"] == (1000, 100)
    assert ratings2["global"] == (1000, 250)

    # Global should be re-initialized
    ratings2["ladder_1v1"] = (500, 100)
    assert ratings2["global"] == (500, 250)


def test_ratings_update_different_leaderboards(
    cyclic_leaderboards,
    chained_leaderboards
):
    ratings1 = PlayerRatings(chained_leaderboards)
    ratings2 = PlayerRatings(cyclic_leaderboards)
    # Global is initialized based on ladder, and should be marked as transient
    ratings1["ladder_1v1"] = (1000, 100)
    assert ratings1["global"] == (1000, 250)

    ratings2.update(ratings1)
    # Existing keys should be copied
    assert ratings2 == {
        "tmm_2v2": (1500, 500),
        "global": (1000, 250),
        "ladder_1v1": (1000, 100)
    }

    # Global should be re-initialized based on a the other rating
    ratings2["ladder_1v1"] = (500, 100)
    ratings2["tmm_2v2"] = (750, 100)
    assert ratings2["global"] == (750, 250)


def test_ratings_update_nontransient_with_transient(chained_leaderboards):
    ratings_t = PlayerRatings(chained_leaderboards)
    ratings_nt = PlayerRatings(chained_leaderboards)

    assert ratings_t["ladder_1v1"] == DEFAULT_RATING
    assert ratings_t["global"] == DEFAULT_RATING
    ratings_nt["ladder_1v1"] = (500, 100)
    ratings_nt["global"] = (1000, 100)
    # Global is not re-initialized
    assert ratings_nt["global"] == (1000, 100)

    ratings_nt.update(ratings_t)
    assert ratings_nt == {"ladder_1v1": DEFAULT_RATING, "global": DEFAULT_RATING}

    ratings_nt["ladder_1v1"] = (750, 100)
    # Now global is re-initialized
    assert ratings_nt["global"] == (750, 250)


def test_ratings_update_transient_with_nontransient(chained_leaderboards):
    ratings_t = PlayerRatings(chained_leaderboards)
    ratings_nt = PlayerRatings(chained_leaderboards)

    assert ratings_t["ladder_1v1"] == DEFAULT_RATING
    assert ratings_t["global"] == DEFAULT_RATING
    ratings_nt["ladder_1v1"] = (500, 100)
    ratings_nt["global"] = (1000, 100)
    # Global is not re-initialized
    assert ratings_nt["global"] == (1000, 100)

    ratings_t.update(ratings_nt)
    assert ratings_t == {"ladder_1v1": (500, 100), "global": (1000, 100)}

    ratings_t["ladder_1v1"] = (750, 100)
    # Global is still not re-initialized
    assert ratings_t["global"] == (1000, 100)
