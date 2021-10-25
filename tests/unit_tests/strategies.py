# Custom hypothesis strategies

import string

from hypothesis import strategies as st

from server.matchmaker import Search
from server.matchmaker.algorithm.team_matchmaker import GameCandidate
from server.rating import Rating
from tests.conftest import make_player


@st.composite
def st_rating(draw):
    """Strategy for generating rating tuples"""
    return Rating(
        draw(st.floats(min_value=-100., max_value=2500.)),
        draw(st.floats(min_value=0.001, max_value=500.))
    )


@st.composite
def st_players(draw, name=None, **kwargs):
    """Strategy for generating Player objects"""
    return make_player(
        ladder_rating=(draw(st_rating())),
        ladder_games=draw(st.integers(0, 1000)),
        login=draw(st.text(
            alphabet=list(string.ascii_letters + string.digits + "_-"),
            min_size=1,
            max_size=42
        )) if name is None else name,
        clan=draw(st.text(min_size=1, max_size=3)),
        **kwargs
    )


@st.composite
def st_searches(draw, num_players=1, **kwargs):
    """Strategy for generating Search objects"""
    return Search([
        draw(st_players(f"p{i}", **kwargs)) for i in range(num_players)
    ])


@st.composite
def st_game_candidates(draw, num_players=1):
    """Strategy for generating GameCandidate objects"""
    player_id = draw(st.integers(min_value=0, max_value=10))
    return GameCandidate(
        (
            draw(st_searches(num_players, player_id=player_id)),
            draw(st_searches(num_players, player_id=player_id + 1))
        ),
        draw(st.floats(min_value=0.0, max_value=1.0))
    )


@st.composite
def st_searches_list(draw, min_players=1, max_players=10, min_size=0, max_size=30):
    """Strategy for generating a list of Search objects"""
    return draw(
        st.lists(
            st_searches(
                num_players=draw(
                    st.integers(min_value=min_players, max_value=max_players)
                )
            ),
            min_size=min_size,
            max_size=max_size
        )
    )


@st.composite
def st_searches_list_with_player_size(draw, min_players=1, max_players=10, min_size=1,  max_size=30):
    """Strategy for generating a list of Search objects and the max player size"""
    player_size = draw(st.integers(min_value=min_players, max_value=max_players))
    searches_list = draw(
        st.lists(
            st_searches(
                num_players=draw(
                    st.integers(min_value=min_players, max_value=player_size)
                )
            ),
            min_size=min_size,
            max_size=max_size
        )
    )
    return searches_list, player_size


@st.composite
def st_searches_list_with_index(draw, min_players=1, max_players=10, min_size=1,  max_size=30):
    """Strategy for generating a list of Search objects and an index that points at a location in the list"""
    searches_list = draw(
        st_searches_list(
            min_players=min_players,
            max_players=max_players,
            min_size=min_size,
            max_size=max_size
        )
    )
    index = draw(st.integers(min_value=0, max_value=max(0, len(searches_list) - 1)))
    return searches_list, index


@st.composite
def st_game_candidates_list(draw, min_players=1, max_players=10, min_size=0, max_size=10):
    """Strategy for generating a list of GameCandidate objects"""
    return draw(
        st.lists(
            st_game_candidates(
                num_players=draw(
                    st.integers(min_value=min_players, max_value=max_players)
                )
            ),
            min_size=min_size,
            max_size=max_size
        )
    )
