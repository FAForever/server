import random

import pytest
from hypothesis import given
from hypothesis import strategies as st
from server.matchmaker import MapPool
from server.types import Map


@pytest.fixture(scope="session")
def map_pool_factory():
    def make(map_pool_id=0, name="Test Pool", maps=[]):
        return MapPool(
            map_pool_id=map_pool_id,
            name=name,
            maps=maps
        )

    return make


def test_choose_map(map_pool_factory):
    map_pool = map_pool_factory(maps=[
        Map(1, "some_map", "maps/some_map.v001.zip"),
        Map(2, "some_map", "maps/some_map.v001.zip"),
        Map(3, "some_map", "maps/some_map.v001.zip"),
        Map(4, "CHOOSE_ME", "maps/choose_me.v001.zip"),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map([1, 2, 3])
        assert chosen_map == (4, "CHOOSE_ME", "maps/choose_me.v001.zip")


def test_choose_map_all_maps_played(map_pool_factory):
    maps = [
        Map(1, "some_map", "maps/some_map.v001.zip"),
        Map(2, "some_map", "maps/some_map.v001.zip"),
        Map(3, "some_map", "maps/some_map.v001.zip"),
    ]
    map_pool = map_pool_factory(maps=maps)

    chosen_map = map_pool.choose_map([1, 2, 3])

    assert chosen_map is not None
    assert chosen_map in maps


def test_choose_map_all_maps_played_not_in_pool(map_pool_factory):
    maps = [
        Map(1, "some_map", "maps/some_map.v001.zip"),
        Map(2, "some_map", "maps/some_map.v001.zip"),
        Map(3, "some_map", "maps/some_map.v001.zip"),
    ]
    map_pool = map_pool_factory(maps=maps)

    # None of the recently played maps are in the current pool
    chosen_map = map_pool.choose_map([4, 5, 6])

    assert chosen_map is not None
    assert chosen_map in maps


def test_choose_map_all_maps_played_returns_least_played(map_pool_factory):
    # Large enough so the test is unlikely to pass by chance
    NUM_MAPS = 1000
    LIMIT = 3

    played_map_ids = [
        # Set up player history so map 1 is played the most
        i + 1 + j for i in range(LIMIT)
        for j in range(NUM_MAPS) if i + 1 + j <= NUM_MAPS
    ]

    maps = [
        Map(i + 1, "some_map", "maps/some_map.v001.zip") for i in range(NUM_MAPS)
    ]
    # Shuffle the list so that `choose_map` can't just return the first map
    random.shuffle(maps)
    map_pool = map_pool_factory(maps=maps)

    chosen_map = map_pool.choose_map(played_map_ids)

    # Map 1 was played only once
    assert chosen_map == (1, "some_map", "maps/some_map.v001.zip")


@given(history=st.lists(st.integers()))
def test_choose_map_single_map(map_pool_factory, history):
    map_pool = map_pool_factory(maps=[
        Map(1, "CHOOSE_ME", "maps/choose_me.v001.zip"),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map(history)
        assert chosen_map == (1, "CHOOSE_ME", "maps/choose_me.v001.zip")


def test_choose_map_raises_on_empty_map_pool(map_pool_factory):
    map_pool = map_pool_factory()

    with pytest.raises(RuntimeError):
        map_pool.choose_map([])
