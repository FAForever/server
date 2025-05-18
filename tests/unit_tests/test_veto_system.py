import pytest

from server.ladder_service.veto_system import _cap_tokens


def test_cap_tokens():
    # Number of tokens is less than all caps
    assert _cap_tokens(
        tokens=3,
        total_remaining=10,
        max_per_map=4,
    ) == 3

    # Number of tokens is more than max per map
    assert _cap_tokens(
        tokens=10,
        total_remaining=10,
        max_per_map=4,
    ) == 4

    # Number of tokens is more than remaining total
    assert _cap_tokens(
        tokens=10,
        total_remaining=1,
        max_per_map=10,
    ) == 1

    # Max per map is zero
    assert _cap_tokens(
        tokens=10,
        total_remaining=5,
        max_per_map=0,
    ) == 5

    # Remaining is zero
    assert _cap_tokens(
        tokens=10,
        total_remaining=0,
        max_per_map=5,
    ) == 0


@pytest.mark.parametrize("M, tokens, expected", [
    # Only 0-token maps, sufficient to meet M
    (2.0, [0, 0, 0], 1.0),
    # Three maps with 0 tokens, M=2 < 3, should return T=1 because taking all 0-token maps is enough

    # Impossible setup, 1 full map required but the only map available is partially vetoed
    (1, [1], 0),
    # function returns 0 for bad input

    # Include maps with 1 token
    (2.0, [0, 1, 1], 2.0),
    # One 0-token map (sum=1) isn't enough for M=2, include two 1-token maps, T=2 satisfies

    # Non-integer M
    (1.5, [0, 1, 1], 4/3),
    # M=1.5, 0-token sum=1 < M, include 1-token maps, T=4/3 ≈ 1.333, sum=1.5

    # Include maps with 2 tokens
    (2.5, [0, 0, 2], 4.0),
    # Two 0-token maps (sum=2) < M=2.5, include 2-token map, T=4, sum=2.5

    # Another test because why not
    (1.9, [0, 1], 10.0),
    # M=1.9, one 0-token (sum=1) < M, include 1-token, final case T=10, sum=1.9

    # More complex case
    (3.5, [0, 0, 1, 1, 2], 8/3),
    # M=3.5, 0 and 1-token maps insufficient, all maps give T=8/3 ≈ 2.667, sum=3.5

    # All maps have 1 token, no 0-token maps
    (1.0, [1, 1, 1], 1.5),
    # T=1.5, each weight=1/3, sum=1

    # All maps have 1 token, small M
    (0.5, [1, 1, 1], 1.2),
    # M=0.5, all 1-token maps, T=1.2, each weight=1/6, sum=0.5

    # Mix of 0 and higher tokens, 0-tokens sufficient
    (1.0, [0, 2], 1.0),
    # M=1, one 0-token map suffices, T=1, sum=1

    # Mix of 0 and 2 tokens
    (1.5, [0, 2], 4.0),
    # M=1.5, 0-token sum=1 < M, include 2-token, T=4, sum=1.5

    # Larger set, T matches next token boundary
    (4.0, [0, 0, 0, 1, 1, 2, 2], 2.0),
    # M=4, 0 and 1-token maps (5 maps), T=2, sum=4

    # Larger set, T in final case
    (5.0, [0, 0, 0, 1, 1, 2, 2], 3.0),
    # M=5, all maps included, T=3, sum=5

    # Float M
    (4.5, [0, 0, 0, 1, 1, 2, 2], 2.4),
    # M=4.5, all maps, T=2.4, sum=4.5

    # The same test, just checking that order of maps doesn't matter
    (4.5, [2, 1, 2, 0, 1, 0, 0], 2.4),
    # M=4.5, all maps, T=2.4, sum=4.5
])
def test_veto_service_calculate_dynamic_tokens_per_map(veto_service, M, tokens, expected):
    result = veto_service.calculate_dynamic_tokens_per_map(M, tokens)
    assert result == pytest.approx(expected, rel=1e-9)
    # Verify that the result produces a sum >= M
    if result != 0:
        total_weight = sum(max((result - v) / result, 0) for v in tokens)
        assert total_weight >= M - 1e-9  # Account for floating-point errors
