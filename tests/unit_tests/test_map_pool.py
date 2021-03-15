import base64
import random
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from server.matchmaker import MapPool
from server.types import Map, NeroxisGeneratedMap


@pytest.fixture(scope="session")
def map_pool_factory():
    def make(map_pool_id=0, name="Test Pool", maps=()):
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
        assert chosen_map == (4, "CHOOSE_ME", "maps/choose_me.v001.zip", 1)


def test_choose_map_with_weights(map_pool_factory):
    map_pool = map_pool_factory(maps=[
        Map(1, "some_map", "maps/some_map.v001.zip", 1),
        Map(2, "some_map", "maps/some_map.v001.zip", 1),
        Map(3, "some_map", "maps/some_map.v001.zip", 1),
        Map(4, "CHOOSE_ME", "maps/choose_me.v001.zip", 10000000),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map()
        assert chosen_map == (4, "CHOOSE_ME", "maps/choose_me.v001.zip", 10000000)


def test_choose_map_generated_map(map_pool_factory):
    version = "0.0.0"
    spawns = 2
    size = 512

    map_pool = map_pool_factory(maps=[
        NeroxisGeneratedMap.of({
            "version": "0.0.0",
            "spawns": 2,
            "size": 512,
            "type": "neroxis"
        }),
    ])

    chosen_map = map_pool.choose_map([])

    map_id = -int.from_bytes(bytes(f'{version}_{spawns}_{size}', encoding="ascii"), 'big')
    size_byte = (size // 64).to_bytes(1, 'big')
    spawn_byte = spawns.to_bytes(1, 'big')
    option_bytes = spawn_byte + size_byte
    option_str = base64.b32encode(option_bytes).decode("ascii").replace("=", "").lower()
    seed_match = "[0-9a-z]{13}"

    assert chosen_map.id == map_id
    assert re.match(f"maps/neroxis_map_generator_{version}_{seed_match}_{option_str}.zip", chosen_map.path)
    assert re.match(f"neroxis_map_generator_{version}_{seed_match}_{option_str}", chosen_map.name)
    assert chosen_map.weight == 1


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


def test_choose_map_all_played_but_generated_map_doesnt_dominate(map_pool_factory):
    maps = [
        Map(1, "some_map", "maps/some_map.v001.zip", 1000000),
        Map(2, "some_map", "maps/some_map.v001.zip", 1000000),
        Map(3, "some_map", "maps/some_map.v001.zip", 1000000),
        NeroxisGeneratedMap.of({
            "version": "0.0.0",
            "spawns": 2,
            "size": 512,
            "type": "neroxis"
        }),
    ]
    map_pool = map_pool_factory(maps=maps)

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map([1, 2, 3])

        assert chosen_map is not None
        assert chosen_map in maps
        assert chosen_map.id in [1, 2, 3]


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
    num_maps = 1000
    limit = 3

    played_map_ids = [
        # Set up player history so map 1 is played the least
        i + 1 + j for i in range(limit)
        for j in range(num_maps) if i + 1 + j <= num_maps
    ]

    maps = [
        Map(i + 1, "some_map", "maps/some_map.v001.zip") for i in range(num_maps)
    ]
    # Shuffle the list so that `choose_map` can't just return the first map
    random.shuffle(maps)
    map_pool = map_pool_factory(maps=maps)

    chosen_map = map_pool.choose_map(played_map_ids)

    # Map 1 was played only once
    assert chosen_map == (1, "some_map", "maps/some_map.v001.zip", 1)


@given(history=st.lists(st.integers()))
def test_choose_map_single_map(map_pool_factory, history):
    map_pool = map_pool_factory(maps=[
        Map(1, "CHOOSE_ME", "maps/choose_me.v001.zip"),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map(history)
        assert chosen_map == (1, "CHOOSE_ME", "maps/choose_me.v001.zip", 1)


def test_choose_map_raises_on_empty_map_pool(map_pool_factory):
    map_pool = map_pool_factory()

    with pytest.raises(RuntimeError):
        map_pool.choose_map([])
