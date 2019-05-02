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
