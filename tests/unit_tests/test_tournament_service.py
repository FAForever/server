from unittest import mock

import pytest
from aio_pika.abc import AbstractIncomingMessage

from server import (
    GameService,
    LadderService,
    LobbyConnection,
    MessageQueueService,
    PlayerService,
    TournamentService,
    config
)
from server.players import PlayerState
from server.tournaments.tournament_game import (
    TournamentGameInfo,
    TournamentGameState
)


async def test_create_tournament_game(game_service: GameService, message_queue_service: MessageQueueService,
                                      player_service: PlayerService, ladder_service: LadderService, player_factory):
    player = player_factory(player_id=1)
    mock_lconn = mock.create_autospec(LobbyConnection)
    player.lobby_connection = mock_lconn
    player_service[player.id] = player
    tournament_service: TournamentService = TournamentService(game_service, message_queue_service, player_service,
                                                              ladder_service)

    message = mock.Mock(AbstractIncomingMessage)
    message.body = """
        {
            "request_id": "9124e8c9-c62f-43c3-bb64-94f3093f2997",
            "game_name": "My game name",
            "participants": [
                {
                    "team": 1,
                    "slot": 1,
                    "faction": 1,
                    "player_id": 1
                }
            ],
            "featured_mod": "faf",
            "map_name": "SCMP_001",
            "game_options": {
                "test": "test"
            }
        }
    """
    message.correlation_id = "9124e8c9-c62f-43c3-bb64-94f3093f2997"
    await tournament_service._create_game(
        message
    )
    assert next(iter(tournament_service._games)).name == "My game name"
    assert next(iter(tournament_service._games)).state == TournamentGameState.CONFIRMATION_PENDING
    mock_lconn.write.assert_called_with(
        {
            'command': 'is_ready',
            'featured_mod': 'faf',
            'game_name': 'My game name',
            'request_id': '9124e8c9-c62f-43c3-bb64-94f3093f2997',
            'response_time_seconds': 30
        }
    )
    assert not mock_lconn.send_warning.called
    assert player.state == PlayerState.STARTING_TOURNAMENT


async def test_create_tournament_game_player_not_idle(game_service: GameService,
                                                      player_service: PlayerService, ladder_service: LadderService,
                                                      player_factory):
    player = player_factory(player_id=1)
    player.state = PlayerState.PLAYING
    mock_lconn = mock.create_autospec(LobbyConnection)
    player.lobby_connection = mock_lconn
    player_service[player.id] = player
    message_queue_mock = mock.create_autospec(MessageQueueService)
    tournament_service: TournamentService = TournamentService(game_service, message_queue_mock, player_service,
                                                              ladder_service)

    message = mock.Mock(AbstractIncomingMessage)
    message.body = """
        {
            "request_id": "9124e8c9-c62f-43c3-bb64-94f3093f2997",
            "game_name": "My game name",
            "participants": [
                {
                    "team": 1,
                    "slot": 1,
                    "faction": 1,
                    "player_id": 1
                }
            ],
            "featured_mod": "faf",
            "map_name": "SCMP_001",
            "game_options": {
                "test": "test"
            }
        }
    """
    message.correlation_id = "9124e8c9-c62f-43c3-bb64-94f3093f2997"
    await tournament_service._create_game(
        message
    )
    message_queue_mock.publish.assert_called_with(
        config.MQ_EXCHANGE_NAME,
        "tourneylauncher.createGame.failed",
        {
            "error_code": "PLAYER_NOT_IDLE",
            "players_causing_cancel": {1}
        },
        correlation_id="9124e8c9-c62f-43c3-bb64-94f3093f2997"
    )
    assert player.state == PlayerState.PLAYING


@pytest.fixture
def tournament_game():
    tournament_game: TournamentGameInfo = mock.create_autospec(TournamentGameInfo)
    tournament_game.request_id = "9124e8c9-c62f-43c3-bb64-94f3093f2997"
    tournament_game.name = "My game name"
    tournament_game.map_name = "SCMP_001"
    tournament_game.players_causing_cancel = set()
    tournament_game.featured_mod = "faf"
    tournament_game.game_options = {}
    tournament_game.state = TournamentGameState.CONFIRMATION_PENDING
    tournament_game.players_ready_ids = set()
    tournament_game.__contains__ = lambda x, y: True
    return tournament_game


class Any:
    def __eq__(self, other):
        return True


async def test_tournament_on_is_ready_response(game_service: GameService, player_service: PlayerService,
                                               player_factory, tournament_game: TournamentGameInfo):
    player = player_factory(player_id=1)
    mock_lconn = mock.create_autospec(LobbyConnection)
    player.lobby_connection = mock_lconn
    player_service[player.id] = player
    message_queue_mock = mock.create_autospec(MessageQueueService)
    ladder_service = mock.create_autospec(LadderService)
    tournament_service: TournamentService = TournamentService(game_service, message_queue_mock, player_service,
                                                              ladder_service)
    tournament_service._games.add(tournament_game)
    tournament_game.players = [player]
    await tournament_service.on_is_ready_response(
        {"request_id": "9124e8c9-c62f-43c3-bb64-94f3093f2997"}, player
    )
    assert not mock_lconn.send_warning.called
    ladder_service.launch_server_made_game.assert_called_once()
    message_queue_mock.publish.assert_called_with(
        config.MQ_EXCHANGE_NAME,
        "tourneylauncher.createGame.success",
        {
            "game_id": Any()
        },
        correlation_id="9124e8c9-c62f-43c3-bb64-94f3093f2997"
    )
    assert len(tournament_service._games) == 0
    assert player.state == PlayerState.STARTING_AUTOMATCH


async def test_tournament_timeout_on_ready(game_service: GameService, player_service: PlayerService,
                                           player_factory, tournament_game: TournamentGameInfo):
    player = player_factory(player_id=1)
    mock_lconn = mock.create_autospec(LobbyConnection)
    player.lobby_connection = mock_lconn
    player_service[player.id] = player
    message_queue_mock = mock.create_autospec(MessageQueueService)
    ladder_service = mock.create_autospec(LadderService)
    tournament_service: TournamentService = TournamentService(game_service, message_queue_mock, player_service,
                                                              ladder_service)
    tournament_game.players = [player]
    tournament_game.is_confirmation_overdue.return_value = True
    tournament_game.get_error_code.return_value = "PLAYER_NOT_CONFIRMING"
    tournament_service._games.add(tournament_game)
    await tournament_service.update_dirties()
    assert not mock_lconn.send_warning.called
    ladder_service.launch_server_made_game.assert_not_called()
    message_queue_mock.publish.assert_called_with(
        config.MQ_EXCHANGE_NAME,
        "tourneylauncher.createGame.failed",
        {
            "error_code": "PLAYER_NOT_CONFIRMING",
            "players_causing_cancel": {1}
        },
        correlation_id="9124e8c9-c62f-43c3-bb64-94f3093f2997"
    )
    assert len(tournament_service._games) == 0
    assert tournament_game.state == TournamentGameState.PLAYER_NOT_CONFIRMING
    assert player.state == PlayerState.IDLE
