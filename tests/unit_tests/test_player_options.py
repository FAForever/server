import pytest

from games.PlayerOptions import PlayerOptions

@pytest.fixture()
def player_options():
    return PlayerOptions()


def test_set_integer_option(player_options):
    player_options[1]["Faction"] = 2
    assert player_options[1]["Faction"] == 2


def test_set_string_option(player_options):
    player_options[1]["RandomOption"] = "RandomValue"
    assert player_options[1]["RandomOption"] == "RandomValue"


def test_move_option(player_options):
    player_options[1]["Faction"] = 2
    player_options.move(1, 2)
    assert player_options[2]["Faction"] == 2