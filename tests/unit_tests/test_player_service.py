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
