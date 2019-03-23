from mock import Mock


async def test_fetch_player_data(player_service):
    player = Mock()
    player.id = 50

    await player_service.fetch_player_data(player)
    assert player.global_rating == (1200, 250)
    assert player.numGames == 42
    assert player.ladder_rating == (1300, 400)
    assert player.clan == '123'
