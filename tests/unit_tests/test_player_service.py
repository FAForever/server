import asynctest
import pytest
from mock import Mock
from server.lobbyconnection import LobbyConnection
from server.rating import RatingType

pytestmark = pytest.mark.asyncio


async def test_fetch_player_data(player_factory, player_service):
    player = player_factory(player_id=50)

    await player_service.fetch_player_data(player)
    assert player.ratings[RatingType.GLOBAL] == (1200, 250)
    assert player.game_count[RatingType.GLOBAL] == 42
    assert player.ratings[RatingType.LADDER_1V1] == (1300, 400)
    assert player.clan == '123'
    assert player.avatar == {'url': 'http://content.faforever.com/faf/avatars/UEF.png', 'tooltip': 'UEF'}


async def test_fetch_player_data_multiple_avatar(player_factory, player_service):
    player1 = player_factory(player_id=51)
    player2 = player_factory(player_id=52)

    await player_service.fetch_player_data(player1)
    assert player1.avatar == {'url': 'http://content.faforever.com/faf/avatars/UEF.png', 'tooltip': 'UEF'}

    await player_service.fetch_player_data(player2)
    assert player2.avatar == {'url': 'http://content.faforever.com/faf/avatars/qai2.png', 'tooltip': 'QAI'}


async def test_fetch_player_data_no_avatar_or_clan(player_factory, player_service):
    player = player_factory(player_id=100)

    await player_service.fetch_player_data(player)
    assert player.ratings[RatingType.GLOBAL] == (1500, 500)
    assert player.game_count[RatingType.GLOBAL] == 0
    assert player.ratings[RatingType.LADDER_1V1] == (1500, 500)
    assert player.clan is None
    assert player.avatar is None


async def test_fetch_player_data_non_existent(player_factory, player_service):
    player = player_factory(player_id=-1)

    await player_service.fetch_player_data(player)


async def test_magic_methods(player_factory, player_service):
    player = player_factory(player_id=0)
    player_service[0] = player

    assert len(player_service) == 1
    assert list(iter(player_service)) == [player]
    assert player_service[0] is player
    assert player_service.get_player(0) is player

    player_service.remove_player(player)

    assert len(player_service) == 0
    assert list(iter(player_service)) == []
    assert player_service[0] is None
    assert player_service.get_player(0) is None


async def test_mark_dirty(player_factory, player_service):
    player = player_factory()
    player_service[0] = player

    # Marking the same player as dirty multiple times should not matter
    player_service.mark_dirty(player)
    assert player_service.dirty_players == {player}
    player_service.mark_dirty(player)
    assert player_service.dirty_players == {player}

    player_service.clear_dirty()
    assert player_service.dirty_players == set()


async def test_update_data(player_factory, player_service):
    await player_service.update_data()

    assert player_service.get_permission_group(1) == 2
    assert player_service.is_uniqueid_exempt(1) is True
    assert player_service.client_version_info == ('0.10.125', 'some-installer.msi')


async def test_broadcast_shutdown(player_factory, player_service):
    player = player_factory()
    lconn = asynctest.create_autospec(LobbyConnection)
    player.lobby_connection = lconn
    player_service[0] = player

    await player_service.shutdown()

    player.lobby_connection.send_warning.assert_called_once()


async def test_broadcast_shutdown_error(player_factory, player_service):
    player = player_factory()
    lconn = asynctest.create_autospec(LobbyConnection)
    lconn.send_warning.side_effect = ValueError
    player.lobby_connection = lconn

    player_service[0] = player

    await player_service.shutdown()

    player.lobby_connection.send_warning.assert_called_once()
