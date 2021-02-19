# Custom hypothesis strategies

import string

from hypothesis import strategies as st

from server.matchmaker import Search
from tests.conftest import make_player


@st.composite
def st_rating(draw):
    """Strategy for generating rating tuples"""
    return (
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
def st_searches(draw, num_players=1):
    """Strategy for generating Search objects"""
    return Search([
        draw(st_players(f"p{i}")) for i in range(num_players)
    ])


@st.composite
def st_searches_list(draw, min_players=1, max_players=10, max_size=30):
    """Strategy for generating a list of Search objects"""
    return draw(
        st.lists(
            st_searches(
                num_players=draw(
                    st.integers(min_value=min_players, max_value=max_players)
                )
            ),
            max_size=max_size
        )
    )
