import asyncio
from unittest import mock

import pytest

from server.config import config
from server.exceptions import ClientError
from server.message_queue_service import MessageQueueService
from server.replay_review_service import (
    MAX_GOAL_LENGTH,
    MAX_LABEL_LENGTH,
    REPLAY_REVIEW_ROUTING_KEY,
    ReplayReviewService,
    parse_review_request
)


@pytest.fixture
def message_queue_service():
    return mock.create_autospec(MessageQueueService)


@pytest.fixture
def service(message_queue_service):
    return ReplayReviewService(message_queue_service)


@pytest.fixture
def valid_message():
    return {
        "command": "request_replay_review",
        "replay_id": 22334455,
        "map": "Seton's Clutch",
        "game_mode": "faf",
        "faction": "UEF",
        "rating": "1100",
        "played_at": "2026-09-05T19:12:00Z",
        "goal": "I want to know why my eco stalls at eight minutes.",
        "struggle": "I never have mass for the second land factory.",
    }


# --- parsing -----------------------------------------------------------------

def test_parse_keeps_the_content_fields(valid_message):
    request = parse_review_request(valid_message)

    assert request == {
        "replay_id": 22334455,
        "goal": "I want to know why my eco stalls at eight minutes.",
        "struggle": "I never have mass for the second land factory.",
        "map": "Seton's Clutch",
        "game_mode": "faf",
        "faction": "UEF",
        "rating": "1100",
        "played_at": "2026-09-05T19:12:00Z",
    }


def test_parse_drops_client_supplied_identity(valid_message):
    """The client does not get to say who it is, at any point."""
    valid_message.update({
        "player_id": 1,
        "login": "Brutus5000",
        "command": "request_replay_review",
    })

    request = parse_review_request(valid_message)

    assert "player_id" not in request
    assert "login" not in request
    assert "command" not in request


def test_parse_fills_missing_labels_with_empty_strings():
    request = parse_review_request({"replay_id": 1, "goal": "help"})

    assert request["map"] == ""
    assert request["struggle"] == ""


@pytest.mark.parametrize("replay_id", [None, "22334455", 0, -1, True, 1.5])
def test_parse_rejects_bad_replay_id(replay_id):
    with pytest.raises(ClientError):
        parse_review_request({"replay_id": replay_id, "goal": "help"})


@pytest.mark.parametrize("goal", [None, "", "   ", "\n\n"])
def test_parse_requires_a_goal(goal):
    with pytest.raises(ClientError):
        parse_review_request({"replay_id": 1, "goal": goal})


def test_parse_rejects_non_text_where_text_belongs():
    with pytest.raises(ClientError):
        parse_review_request({"replay_id": 1, "goal": "help", "map": 5})


def test_parse_rejects_overlong_free_text():
    with pytest.raises(ClientError):
        parse_review_request({
            "replay_id": 1,
            "goal": "a" * (MAX_GOAL_LENGTH + 1),
        })


def test_parse_rejects_overlong_labels():
    with pytest.raises(ClientError):
        parse_review_request({
            "replay_id": 1,
            "goal": "help",
            "map": "a" * (MAX_LABEL_LENGTH + 1),
        })


def test_parse_strips_control_characters_but_keeps_paragraphs():
    request = parse_review_request({
        "replay_id": 1,
        "goal": "first line\n\nsecond line\x07\x00",
    })

    assert request["goal"] == "first line\n\nsecond line"


# --- publishing --------------------------------------------------------------

async def test_submit_publishes_with_server_stamped_identity(
    service, message_queue_service, player_factory, valid_message
):
    player = player_factory("Rhiza", player_id=4242)

    await service.submit(player, parse_review_request(valid_message))

    message_queue_service.publish.assert_called_once()
    exchange, routing_key, payload = message_queue_service.publish.call_args[0]

    assert exchange == config.MQ_EXCHANGE_NAME
    assert routing_key == REPLAY_REVIEW_ROUTING_KEY
    assert payload["player_id"] == 4242
    assert payload["login"] == "Rhiza"
    assert payload["replay_id"] == 22334455
    assert "requested_at" in payload


async def test_submit_ignores_identity_the_client_tried_to_set(
    service, message_queue_service, player_factory, valid_message
):
    """
    A client that sends its own `player_id` gets the connection's anyway.

    This is the property the whole design rests on, so it is asserted end to
    end rather than only at the parser.
    """
    valid_message["player_id"] = 1
    valid_message["login"] = "Brutus5000"
    player = player_factory("Rhiza", player_id=4242)

    await service.submit(player, parse_review_request(valid_message))

    payload = message_queue_service.publish.call_args[0][2]
    assert payload["player_id"] == 4242
    assert payload["login"] == "Rhiza"


async def test_submit_rate_limits_per_player(
    service, message_queue_service, player_factory, valid_message
):
    player = player_factory("Rhiza", player_id=4242)
    request = parse_review_request(valid_message)

    await service.submit(player, request, now=0.0)
    with pytest.raises(ClientError):
        await service.submit(player, request, now=60.0)

    assert message_queue_service.publish.call_count == 1


async def test_a_rejected_request_never_reaches_the_bus(
    service, message_queue_service, player_factory, valid_message
):
    player = player_factory("Rhiza", player_id=4242)
    request = parse_review_request(valid_message)

    await service.submit(player, request, now=0.0)
    message_queue_service.publish.reset_mock()

    with pytest.raises(ClientError):
        await service.submit(player, request, now=1.0)

    message_queue_service.publish.assert_not_called()


async def test_other_players_are_not_rate_limited(
    service, message_queue_service, player_factory, valid_message
):
    request = parse_review_request(valid_message)

    await service.submit(player_factory("Rhiza", player_id=1), request, now=0.0)
    await service.submit(player_factory("Sheikah", player_id=2), request, now=1.0)

    assert message_queue_service.publish.call_count == 2


async def test_the_cooldown_expires(
    service, message_queue_service, player_factory, valid_message
):
    player = player_factory("Rhiza", player_id=4242)
    request = parse_review_request(valid_message)

    await service.submit(player, request, now=0.0)
    await service.submit(
        player, request, now=config.REPLAY_REVIEW_COOLDOWN_SECONDS + 1
    )

    assert message_queue_service.publish.call_count == 2


async def test_expired_entries_do_not_accumulate(
    service, player_factory, valid_message
):
    request = parse_review_request(valid_message)

    for player_id in range(10):
        await service.submit(
            player_factory(f"Player{player_id}", player_id=player_id),
            request,
            now=float(player_id),
        )
    assert len(service._last_accepted) == 10

    await service.submit(
        player_factory("Latecomer", player_id=99),
        request,
        now=config.REPLAY_REVIEW_COOLDOWN_SECONDS + 100,
    )
    assert len(service._last_accepted) == 1


async def test_a_publish_that_fails_does_not_cost_the_player_their_turn(
    service, message_queue_service, player_factory, valid_message
):
    player = player_factory("Rhiza", player_id=4242)
    request = parse_review_request(valid_message)
    message_queue_service.publish.side_effect = ConnectionError("broker down")

    with pytest.raises(ConnectionError):
        await service.submit(player, request, now=0.0)

    message_queue_service.publish.side_effect = None
    await service.submit(player, request, now=1.0)

    assert message_queue_service.publish.call_count == 2


async def test_two_requests_in_flight_at_once_publish_once(
    service, message_queue_service, player_factory, valid_message
):
    """The cooldown is claimed before publishing, not after it returns."""
    player = player_factory("Rhiza", player_id=4242)
    request = parse_review_request(valid_message)

    release = asyncio.Event()

    async def block(*args, **kwargs):
        await release.wait()

    message_queue_service.publish.side_effect = block

    first = asyncio.create_task(service.submit(player, request, now=0.0))
    # Let the first request reach the publish and suspend there.
    await asyncio.sleep(0)

    with pytest.raises(ClientError):
        await service.submit(player, request, now=1.0)

    release.set()
    await first

    assert message_queue_service.publish.call_count == 1
