from unittest import mock

import pytest
from server import GameService, PlayerService, run_lobby_server


@pytest.fixture
def mock_players(db_engine):
    m = mock.create_autospec(PlayerService())
    m.client_version_info = (0, None)
    return m


@pytest.fixture
def mock_games(mock_players):
    return mock.create_autospec(GameService(mock_players))


@pytest.fixture
def lobby_server(request, loop, db_engine, player_service, game_service, geoip_service):
    ctx = run_lobby_server(
        address=('127.0.0.1', None),
        geoip_service=geoip_service,
        player_service=player_service,
        games=game_service,
        loop=loop
    )
    player_service.is_uniqueid_exempt = lambda id: True

    def fin():
        ctx.close()
        loop.run_until_complete(ctx.wait_closed())

    request.addfinalizer(fin)

    return ctx
