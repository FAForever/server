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
        Map(1, "some_map.v001", map_pool_map_version_id=1),
        Map(2, "some_map.v001", map_pool_map_version_id=2),
        Map(3, "some_map.v001", map_pool_map_version_id=3),
        Map(4, "choose_me.v001", map_pool_map_version_id=4),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map([1, 2, 3])
        assert chosen_map == Map(4, "choose_me.v001", map_pool_map_version_id=4)


@pytest.mark.flaky
def test_choose_map_with_weights(map_pool_factory):
    map_pool = map_pool_factory(maps=[
        Map(1, "some_map.v001", weight=1, map_pool_map_version_id=1),
        Map(2, "some_map.v001", weight=1, map_pool_map_version_id=2),
        Map(3, "some_map.v001", weight=1, map_pool_map_version_id=3),
        Map(4, "choose_me.v001", weight=10000000, map_pool_map_version_id=4),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map()
        assert chosen_map == Map(4, "choose_me.v001", weight=10000000, map_pool_map_version_id=4)


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
        }, map_pool_map_version_id=1),
    ])

    chosen_map = map_pool.choose_map([])

    map_id = -int.from_bytes(bytes(f"{version}_{spawns}_{size}", encoding="ascii"), "big")
    size_byte = (size // 64).to_bytes(1, "big")
    spawn_byte = spawns.to_bytes(1, "big")
    option_bytes = spawn_byte + size_byte
    option_str = base64.b32encode(option_bytes).decode("ascii").replace("=", "").lower()
    seed_match = "[0-9a-z]{13}"

    assert chosen_map.id == map_id
    assert re.match(
        f"maps/neroxis_map_generator_{version}_{seed_match}_{option_str}.zip",
        chosen_map.file_path,
    )
    assert re.match(
        f"neroxis_map_generator_{version}_{seed_match}_{option_str}",
        chosen_map.folder_name,
    )
    assert chosen_map.ranked is True
    assert chosen_map.weight == 1


def test_choose_map_all_maps_played(map_pool_factory):
    maps = [
        Map(1, "some_map.v001", map_pool_map_version_id=1),
        Map(2, "some_map.v001", map_pool_map_version_id=2),
        Map(3, "some_map.v001", map_pool_map_version_id=3),
    ]
    map_pool = map_pool_factory(maps=maps)

    chosen_map = map_pool.choose_map([1, 2, 3])

    assert chosen_map is not None
    assert chosen_map in maps


def test_choose_map_all_played_except_generated_map(map_pool_factory):
    generated_map = NeroxisGeneratedMap.of({
        "version": "0.0.0",
        "spawns": 2,
        "size": 512,
        "type": "neroxis"
    })
    maps = [
        Map(1, "some_map.v001", weight=1000000, map_pool_map_version_id=1),
        Map(2, "some_map.v001", weight=1000000, map_pool_map_version_id=2),
        Map(3, "some_map.v001", weight=1000000, map_pool_map_version_id=3),
        generated_map,
    ]
    map_pool = map_pool_factory(maps=maps)

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map([1, 2, 3])

        assert chosen_map is not None
        assert chosen_map.id == generated_map.id


def test_choose_map_all_maps_played_not_in_pool(map_pool_factory):
    maps = [
        Map(1, "some_map.v001", map_pool_map_version_id=1),
        Map(2, "some_map.v001", map_pool_map_version_id=2),
        Map(3, "some_map.v001", map_pool_map_version_id=3),
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
        Map(i + 1, "some_map.v001", map_pool_map_version_id=i+1) for i in range(num_maps)
    ]
    # Shuffle the list so that `choose_map` can't just return the first map
    random.shuffle(maps)
    map_pool = map_pool_factory(maps=maps)

    chosen_map = map_pool.choose_map(played_map_ids)

    # Map 1 was played only once
    assert chosen_map == Map(1, "some_map.v001", map_pool_map_version_id=1)


@given(history=st.lists(st.integers()))
def test_choose_map_single_map(map_pool_factory, history):
    map_pool = map_pool_factory(maps=[
        Map(1, "choose_me.v001", map_pool_map_version_id=1),
    ])

    # Make the probability very low that the test passes because we got lucky
    for _ in range(20):
        chosen_map = map_pool.choose_map(history)
        assert chosen_map == Map(1, "choose_me.v001", map_pool_map_version_id=1)


def test_choose_map_raises_on_empty_map_pool(map_pool_factory):
    map_pool = map_pool_factory()

    with pytest.raises(RuntimeError):
        map_pool.choose_map([])


@pytest.mark.parametrize(
    "initial_weights, played_map_ids, base_thresholds, repeat_factor, expected_adjusted_weights",
    [
        # All Maps Played Equally
        (
            {1: 1, 2: 1, 3: 1},
            [1, 2, 3],
            [0.5],
            0.8,
            {1: 1, 2: 1, 3: 1}
        ),
        # Testing Redistribution: should be proportional to initial weights
        (
            {1: 0.6, 2: 0.5, 3: 1},
            [1],
            [0.5],
            0.8,
            {1: 0, 2: 0.7, 3: 1.4}
        ),
        # High Threshold, No Redistribution to half-banned map
        (
            {1: 1, 2: 1, 3: 0.5},
            [1, 1, 2],
            [1],
            0.8,
            {1: 0, 2: 2, 3: 0.5}
        ),
        # Low first Threshold, Redistribution to half-banned map happens
        (
            {1: 1, 2: 1, 3: 0.5},
            [1, 1, 2],
            [0.5],
            0.8,
            {1: 0, 2: 0, 3: 2.5}
        ),
        # Secondary Threshold triggers Redistribution with help of repeat_factor
        (
            {1: 1, 2: 0.8, 3: 0.4},
            [1, 1, 2],
            [1, 0.5],
            0.8,
            {1: 0, 2: 0, 3: 2.2}
        ),
        # Threshold is very high but repeat_factor handles high playcounts
        (
            {1: 1, 2: 0.9 * 0.8 ** 7},
            [1] * 8,
            [0.9],
            0.8,
            {1: 0, 2: 1 + 0.9 * 0.8 ** 7}
        ),
        # Empty Played Map IDs
        (
            {1: 1, 2: 1, 3: 1},
            [],
            [0.5],
            0.8,
            {1: 1, 2: 1, 3: 1}
        ),
        # Played Maps Not in Pool
        (
            {1: 1, 2: 1, 3: 1},
            [1, 1, 4],
            [0.5],
            0.8,
            {1: 0, 2: 1.5, 3: 1.5}
        ),
        # Really complex redistribution test
        # 1 -> [5,6], [2,3] -> [5,6,8], [7,9] -> 5
        (
            {1: 0.9, 2: 0.6, 3: 0.4, 4: 0.2, 5: 0.75, 6: 0.6, 7: 1, 8: 0.5, 9: 1},
            [1, 1, 2, 3, 7, 9],
            [0.75, 0.5],
            0.8,
            {
                1: 0,
                2: 0,
                3: 0,
                4: 0.2,
                5: pytest.approx(3.655405, rel=1e-6),
                6: pytest.approx(1.324324, rel=1e-6),
                7: 0,
                8: pytest.approx(0.770270, rel=1e-6),
                9: 0
            }
        ),
        # Same test but maps and played_ids are in the different order
        (
            {4: 0.2, 9: 1, 7: 1, 6: 0.6, 5: 0.75, 8: 0.5, 1: 0.9, 3: 0.4, 2: 0.6},
            [9, 7, 2, 1, 3, 1],
            [0.75, 0.5],
            0.8,
            {
                1: 0,
                2: 0,
                3: 0,
                4: 0.2,
                5: pytest.approx(3.655405, rel=1e-6),
                6: pytest.approx(1.324324, rel=1e-6),
                7: 0,
                8: pytest.approx(0.770270, rel=1e-6),
                9: 0
            }
        ),
    ],
)
def test_apply_antirepetition_adjustment(map_pool_factory, initial_weights, played_map_ids, base_thresholds, repeat_factor, expected_adjusted_weights):
    map_pool = map_pool_factory()
    adjusted = map_pool.apply_antirepetition_adjustment(initial_weights, played_map_ids, base_thresholds, repeat_factor)
    assert adjusted == expected_adjusted_weights
