from server import GameService, PlayerService, ServerInstance


def test_auto_create_services():
    instance = ServerInstance("TestCreateServices", None, None, None)

    assert instance.services != {}
    assert isinstance(instance.services["player_service"], PlayerService)
    assert isinstance(instance.services["game_service"], GameService)
