import dataclasses
import json
from unittest import mock

import pytest

from server.game_launch_service import (
    GameLaunchService,
    MatchLaunchStatus,
    MatchPlayer,
    MatchSpec
)
from server.games import LadderGame
from server.games.ladder_game import GameClosedError
from server.players import PlayerState
from server.types import Map


@pytest.fixture
def players(player_factory, player_service):
    p1 = player_factory("Dostya", player_id=1, lobby_connection_spec="auto")
    p2 = player_factory("Rhiza", player_id=2, lobby_connection_spec="auto")
    player_service[p1.id] = p1
    player_service[p2.id] = p2
    return p1, p2


def make_spec(**kwargs) -> MatchSpec:
    args = dict(
        name="Dostya Vs Rhiza",
        featured_mod="faf",
        rating_type="ladder_1v1",
        map=Map(15, "scmp_015", ranked=True, map_pool_map_version_id=3),
        host_id=1,
        players=(
            MatchPlayer(player_id=1, team=2, slot=1, faction=1),
            MatchPlayer(player_id=2, team=3, slot=2, faction=3),
        ),
        matchmaker_queue_id=1,
        game_options={"Share": "ShareUntilDeath"},
    )
    args.update(kwargs)
    return MatchSpec(**args)


@pytest.fixture
def mock_launch(monkeypatch):
    monkeypatch.setattr(LadderGame, "wait_hosted", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "wait_launched", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "timeout_game", mock.AsyncMock())
    monkeypatch.setattr(LadderGame, "on_game_finish", mock.AsyncMock())


def test_match_spec_is_json_serializable():
    spec = make_spec()

    data = json.loads(json.dumps(dataclasses.asdict(spec)))

    assert data["host_id"] == 1
    assert data["players"][1] == {
        "player_id": 2,
        "team": 3,
        "slot": 2,
        "faction": 3,
    }


async def test_create_match(
    game_launch_service: GameLaunchService,
    game_service,
    players,
    mock_launch,
):
    p1, p2 = players

    result = await game_launch_service.create_match(make_spec())

    assert result.is_successful
    game = game_service[result.game_id]
    assert isinstance(game, LadderGame)
    assert game.name == "Dostya Vs Rhiza"
    assert game.host is p1
    assert game.max_players == 2
    assert game.matchmaker_queue_id == 1
    assert game.game_options["Share"] == "ShareUntilDeath"
    assert game.get_player_option(2, "Team") == 3
    assert game.get_player_option(2, "StartSpot") == 2
    assert game.get_player_option(2, "Faction") == 3

    p1.lobby_connection.write_launch_game.assert_called_once_with(
        game, is_host=True, options=mock.ANY
    )
    p2.lobby_connection.write_launch_game.assert_called_once_with(
        game, is_host=False, options=mock.ANY
    )
    options = p2.lobby_connection.write_launch_game.call_args.kwargs["options"]
    assert options.mapname == "scmp_015"
    assert options.map_position == 2
    assert options.map_pool_map_version_id == 3
    assert p1.state is PlayerState.STARTING_AUTOMATCH
    assert p2.state is PlayerState.STARTING_AUTOMATCH
    LadderGame.on_game_finish.assert_not_called()


@pytest.mark.parametrize("spec", (
    make_spec(host_id=3),
    make_spec(players=(
        MatchPlayer(player_id=1, team=2, slot=1, faction=1),
        MatchPlayer(player_id=1, team=3, slot=2, faction=1),
    )),
))
async def test_create_match_invalid_spec(
    game_launch_service: GameLaunchService,
    game_service,
    players,
    spec,
):
    game_id = game_service.game_id_counter

    result = await game_launch_service.create_match(spec)

    assert result.status is MatchLaunchStatus.ERRORED
    assert game_service.game_id_counter == game_id


async def test_create_match_player_busy(
    game_launch_service: GameLaunchService,
    game_service,
    players,
):
    p1, p2 = players
    p2.state = PlayerState.HOSTING
    game_id = game_service.game_id_counter

    result = await game_launch_service.create_match(make_spec())

    assert result.status is MatchLaunchStatus.PLAYERS_UNAVAILABLE
    assert result.player_ids == (2,)
    assert result.game_id is None
    assert game_service.game_id_counter == game_id
    assert p1.state is PlayerState.IDLE
    assert p2.state is PlayerState.HOSTING
    p1.lobby_connection.write_launch_game.assert_not_called()


async def test_create_match_player_offline(
    game_launch_service: GameLaunchService,
    game_service,
    player_service,
    players,
):
    p1, p2 = players
    player_service.remove_player(p2)
    game_id = game_service.game_id_counter

    result = await game_launch_service.create_match(make_spec())

    assert result.status is MatchLaunchStatus.NOT_CONNECTED
    assert result.player_ids == (2,)
    assert game_service.game_id_counter == game_id
    assert p1.state is PlayerState.IDLE
    p1.lobby_connection.write_launch_game.assert_not_called()


async def test_create_match_game_closed(
    game_launch_service: GameLaunchService,
    players,
    mock_launch,
):
    p1, p2 = players
    LadderGame.wait_launched.side_effect = GameClosedError(p2)

    result = await game_launch_service.create_match(make_spec())

    assert result.status is MatchLaunchStatus.ABORTED_BY_PLAYER
    assert result.player_ids == (2,)
    assert result.game_id is not None
    LadderGame.on_game_finish.assert_called_once()
    # Neither player got a game connection, so they are released right away
    assert p1.state is PlayerState.IDLE
    assert p2.state is PlayerState.IDLE


async def test_create_match_errored(
    game_launch_service: GameLaunchService,
    players,
    mock_launch,
):
    p1, p2 = players
    LadderGame.wait_launched.side_effect = RuntimeError("Boom")

    result = await game_launch_service.create_match(make_spec())

    assert result.status is MatchLaunchStatus.ERRORED
    assert result.player_ids == ()
    LadderGame.on_game_finish.assert_called_once()
    assert p1.state is PlayerState.IDLE
    assert p2.state is PlayerState.IDLE
