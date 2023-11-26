from server.config import config
from server.matchmaker import PopTimer


def test_queue_time_until_next_pop(queue_factory):
    team_size = 2
    t1 = PopTimer(queue_factory(team_size=team_size))
    t2 = PopTimer(queue_factory(team_size=team_size))

    desired_players = config.QUEUE_POP_DESIRED_MATCHES * team_size * 2

    assert t1.time_until_next_pop(0, 0) == config.QUEUE_POP_TIME_MAX
    # If the desired number of players is not reached within the maximum waiting
    # time, then the next round must wait for the maximum allowed time as well.
    a1 = t1.time_until_next_pop(
        num_queued=desired_players - 1,
        time_queued=config.QUEUE_POP_TIME_MAX
    )
    assert a1 == config.QUEUE_POP_TIME_MAX

    # If there are more players than expected, the time should drop
    a2 = t1.time_until_next_pop(
        num_queued=desired_players * 2,
        time_queued=config.QUEUE_POP_TIME_MAX
    )
    assert a2 < a1

    # Make sure that queue moving averages are calculated independently
    assert t2.time_until_next_pop(0, 0) == config.QUEUE_POP_TIME_MAX


def test_queue_pop_time_moving_average_size(queue_factory):
    t1 = PopTimer(queue_factory())

    for _ in range(100):
        t1.time_until_next_pop(100, 1)

    # The rate should be extremely high, meaning the pop time should be low
    assert t1.time_until_next_pop(100, 1) == config.QUEUE_POP_TIME_MIN

    for _ in range(config.QUEUE_POP_TIME_MOVING_AVG_SIZE):
        t1.time_until_next_pop(0, 100)

    # The rate should be extremely low, meaning the pop time should be high
    assert t1.time_until_next_pop(0, 100) == config.QUEUE_POP_TIME_MAX
