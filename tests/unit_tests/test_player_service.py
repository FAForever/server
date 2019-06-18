from mock import Mock


async def test_fetch_player_data(player_service):
    player = Mock()
    player.id = 50

    await player_service.fetch_player_data(player)
    assert player.global_rating == (1200, 250)
    assert player.numGames == 42
    assert player.ladder_rating == (1300, 400)
    assert player.clan == '123'
    assert player.avatar == {'url': 'http://content.faforever.com/faf/avatars/UEF.png', 'tooltip': 'UEF'}


async def test_fetch_player_data_multiple_avatar(player_service):
    player1 = Mock()
    player1.id = 51
    player2 = Mock()
    player2.id = 52

    await player_service.fetch_player_data(player1)
    assert player1.avatar == {'url': 'http://content.faforever.com/faf/avatars/UEF.png', 'tooltip': 'UEF'}

    await player_service.fetch_player_data(player2)
    assert player2.avatar == {'url': 'http://content.faforever.com/faf/avatars/qai2.png', 'tooltip': 'QAI'}


async def test_fetch_player_data_no_avatar_or_clan(player_service):
    player = Mock()
    player.id = 100

    await player_service.fetch_player_data(player)
    assert player.global_rating == (1500, 500)
    assert player.numGames == 0
    assert player.ladder_rating == (1500, 500)
    player.clan is None
    player.avatar.assert_not_called()


async def test_fetch_player_data_non_existent(player_service):
    player = Mock()
    player.id = -1

    await player_service.fetch_player_data(player)


def test_magic_methods(player_service):
    player = Mock()
    player.id = 0
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


def test_mark_dirty(player_service):
    player = Mock()
    player_service[0] = player

    # Marking the same player as dirty multiple times should not matter
    player_service.mark_dirty(player)
    assert player_service.dirty_players == {player}
    player_service.mark_dirty(player)
    assert player_service.dirty_players == {player}

    player_service.clear_dirty()
    assert player_service.dirty_players == set()


async def test_update_data(player_service):
    await player_service.update_data()

    assert player_service.get_permission_group(1) == 2
    assert player_service.is_uniqueid_exempt(1) is True
    assert player_service.client_version_info == ('0.10.125', 'some-installer.msi')


def test_broadcast_shutdown(player_service):
    player = Mock()
    player_service[0] = player

    player_service.broadcast_shutdown()

    player.lobby_connection.send_warning.assert_called_once()


def test_broadcast_shutdown_error(player_service):
    player = Mock()
    player.lobby_connection.send_warning.side_effect = ValueError
    player_service[0] = player

    player_service.broadcast_shutdown()

    player.lobby_connection.send_warning.assert_called_once()
