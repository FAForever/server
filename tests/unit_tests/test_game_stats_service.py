from unittest.mock import Mock, MagicMock
import pytest
from faf.factions import Faction
from server.games.game import Game, GameState
from server.lobbyconnection import LobbyConnection
from server.players import Player
from server.stats.achievement_service import *
from server.stats.event_service import *
from server.stats.game_stats_service import *
from tests import CoroMock
from tests.unit_tests.conftest import add_connected_player
from tests.unit_tests.game_fixtures import game as base_game


@pytest.fixture()
def event_service():
    m = Mock(spec=EventService)
    m.execute_batch_update = CoroMock()
    return m


@pytest.fixture()
def achievement_service():
    m = Mock(spec=AchievementService)
    m.execute_batch_update = CoroMock()
    return m


@pytest.fixture()
def game_stats_service(event_service, achievement_service):
    return GameStatsService(event_service, achievement_service)


@pytest.fixture()
def player():
    player = Player(login="TestUser", id=42)
    player._lobby_connection = MagicMock(spec=LobbyConnection)
    return player


@pytest.fixture()
def game(loop, base_game, player):
    base_game.state = GameState.LOBBY
    add_connected_player(base_game, player)
    base_game.set_player_option(player.id, 'Army', 1)
    base_game.host = player
    loop.run_until_complete(base_game.launch())
    loop.run_until_complete(base_game.add_result(player, 1, 'victory', 10))
    return base_game


@pytest.fixture()
def unit_stats():
    return {
        'air': {'built': 0, 'lost': 0, 'kills': 0},
        'land': {'built': 0, 'lost': 0, 'kills': 0},
        'naval': {'built': 0, 'lost': 0, 'kills': 0},
        'experimental': {'built': 0, 'lost': 0, 'kills': 0},
        'transportation': {'built': 0, 'lost': 0, 'kills': 0},
        'sacu': {'built': 0, 'lost': 0, 'kills': 0},
        'cdr': {'built': 1, 'lost': 0, 'kills': 0},
        'tech1': {'built': 0, 'lost': 0, 'kills': 0},
        'tech2': {'built': 0, 'lost': 0, 'kills': 0},
        'tech3': {'built': 0, 'lost': 0, 'kills': 0},
        'engineer': {'built': 0, 'lost': 0, 'kills': 0}
    }


async def test_process_game_stats(game_stats_service, event_service, achievement_service, player, game):
    
    with open("tests/data/game_stats_full_example.json", "r") as stats_file:
        stats = stats_file.read()

    await game_stats_service.process_game_stats(player, game, stats)

    event_service.record_event.assert_any_call(EVENT_LOST_ACUS, 0, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_AIR_UNITS, 1, [])
    event_service.record_event.assert_any_call(EVENT_LOST_AIR_UNITS, 2, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_LAND_UNITS, 4, [])
    event_service.record_event.assert_any_call(EVENT_LOST_LAND_UNITS, 5, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_NAVAL_UNITS, 33, [])
    event_service.record_event.assert_any_call(EVENT_LOST_NAVAL_UNITS, 11, [])
    event_service.record_event.assert_any_call(EVENT_LOST_TECH_1_UNITS, 12, [])
    event_service.record_event.assert_any_call(EVENT_LOST_TECH_2_UNITS, 13, [])
    event_service.record_event.assert_any_call(EVENT_LOST_TECH_3_UNITS, 14, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_TECH_1_UNITS, 16, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_TECH_2_UNITS, 17, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_TECH_3_UNITS, 18, [])
    event_service.record_event.assert_any_call(EVENT_LOST_EXPERIMENTALS, 19, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_EXPERIMENTALS, 20, [])
    event_service.record_event.assert_any_call(EVENT_LOST_ENGINEERS, 21, [])
    event_service.record_event.assert_any_call(EVENT_BUILT_ENGINEERS, 22, [])
    event_service.record_event.assert_any_call(EVENT_SERAPHIM_PLAYS, 1, [])
    event_service.record_event.assert_any_call(EVENT_SERAPHIM_WINS, 1, [])
    event_service.execute_batch_update.assert_called_once_with(42, [])

    achievement_service.increment.assert_any_call(ACH_NOVICE, 1, [])
    achievement_service.increment.assert_any_call(ACH_JUNIOR, 1, [])
    achievement_service.increment.assert_any_call(ACH_SENIOR, 1, [])
    achievement_service.increment.assert_any_call(ACH_VETERAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_ADDICT, 1, [])
    achievement_service.increment.assert_any_call(ACH_THAAM, 1, [])
    achievement_service.increment.assert_any_call(ACH_YENZYNE, 1, [])
    achievement_service.increment.assert_any_call(ACH_SUTHANUS, 1, [])
    achievement_service.increment.assert_any_call(ACH_DONT_MESS_WITH_ME, 3, [])
    achievement_service.unlock.assert_any_call(ACH_HATTRICK, [])
    achievement_service.increment.assert_any_call(ACH_NO_MERCY, 154, [])
    achievement_service.increment.assert_any_call(ACH_DEADLY_BUGS, 147, [])
    achievement_service.unlock.assert_any_call(ACH_RAINMAKER, [])
    achievement_service.unlock.assert_any_call(ACH_NUCLEAR_WAR, [])
    achievement_service.unlock.assert_any_call(ACH_SO_MUCH_RESOURCES, [])
    achievement_service.increment.assert_any_call(ACH_IT_AINT_A_CITY, 47, [])
    achievement_service.increment.assert_any_call(ACH_STORMY_SEA, 74, [])
    achievement_service.unlock.assert_any_call(ACH_MAKE_IT_HAIL, [])
    achievement_service.unlock.assert_any_call(ACH_I_HAVE_A_CANON, [])
    achievement_service.increment.assert_any_call(ACH_LANDLUBBER, 1, [])
    achievement_service.increment.assert_any_call(ACH_SEAMAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_ADMIRAL_OF_THE_FLEET, 1, [])
    achievement_service.increment.assert_any_call(ACH_DEATH_FROM_ABOVE, 71, [])
    achievement_service.increment.assert_any_call(ACH_ASS_WASHER, 37, [])
    achievement_service.increment.assert_any_call(ACH_ALIEN_INVASION, 41, [])
    achievement_service.increment.assert_any_call(ACH_FATTER_IS_BETTER, 73, [])
    achievement_service.increment.assert_any_call(ACH_ARACHNOLOGIST, 87, [])
    achievement_service.increment.assert_any_call(ACH_INCOMING_ROBOTS, 83, [])
    achievement_service.increment.assert_any_call(ACH_FLYING_DEATH, 49, [])
    achievement_service.increment.assert_any_call(ACH_HOLY_CRAB, 51, [])
    achievement_service.increment.assert_any_call(ACH_THE_TRANSPORTER, 101, [])
    achievement_service.increment.assert_any_call(ACH_DR_EVIL, 20, [])
    achievement_service.increment.assert_any_call(ACH_TECHIE, 1, [])
    achievement_service.increment.assert_any_call(ACH_I_LOVE_BIG_TOYS, 1, [])
    achievement_service.increment.assert_any_call(ACH_EXPERIMENTALIST, 1, [])
    achievement_service.set_steps_at_least.assert_any_call(ACH_WHO_NEEDS_SUPPORT, 110, [])
    achievement_service.set_steps_at_least.assert_any_call(ACH_WHAT_A_SWARM, 198, [])
    achievement_service.unlock.assert_any_call(ACH_THAT_WAS_CLOSE, [])
    achievement_service.execute_batch_update.assert_called_once_with(42, [])

    # In decent mock frameworks, there exists a "assert_no_more_interactions"
    assert len(achievement_service.mock_calls) == 38
    assert len(event_service.mock_calls) == 19
    assert achievement_service.execute_batch_update.called
    assert event_service.execute_batch_update.called


async def test_process_game_stats_single_player(game_stats_service, player, game, achievement_service, event_service):
    with open("tests/data/game_stats_single_player.json", "r") as stats_file:
        stats = stats_file.read()

    await game_stats_service.process_game_stats(player, game, stats)
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


async def test_process_game_stats_ai_game(game_stats_service, player, game, achievement_service, event_service):
    with open("tests/data/game_stats_ai_game.json", "r") as stats_file:
        stats = stats_file.read()

    await game_stats_service.process_game_stats(player, game, stats)
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


async def test_process_game_won_ladder1v1(game_stats_service, player, game, achievement_service):
    game.game_mode = 'ladder1v1'

    with open("tests/data/game_stats_simple_win.json", "r") as stats_file:
        stats = stats_file.read()

    await game_stats_service.process_game_stats(player, game, stats)

    achievement_service.unlock.assert_any_call(ACH_FIRST_SUCCESS, [])


def test_category_stats_won_more_air(game_stats_service, player, achievement_service, unit_stats):
    unit_stats['air']['built'] = 3
    unit_stats['land']['built'] = 2
    unit_stats['naval']['built'] = 1

    game_stats_service._category_stats(unit_stats, True, [], [])

    achievement_service.increment.assert_any_call(ACH_WRIGHT_BROTHER, 1, [])
    achievement_service.increment.assert_any_call(ACH_WINGMAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_KING_OF_THE_SKIES, 1, [])
    assert len(achievement_service.mock_calls) == 3


def test_category_stats_won_more_land(game_stats_service, player, achievement_service, unit_stats):
    unit_stats['air']['built'] = 2
    unit_stats['land']['built'] = 3
    unit_stats['naval']['built'] = 1

    game_stats_service._category_stats(unit_stats, True, [], [])

    achievement_service.increment.assert_any_call(ACH_MILITIAMAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_GRENADIER, 1, [])
    achievement_service.increment.assert_any_call(ACH_FIELD_MARSHAL, 1, [])
    assert len(achievement_service.mock_calls) == 3


def test_category_stats_won_more_naval(game_stats_service, player, achievement_service, unit_stats):
    unit_stats['air']['built'] = 2
    unit_stats['land']['built'] = 1
    unit_stats['naval']['built'] = 3

    game_stats_service._category_stats(unit_stats, True, [], [])

    achievement_service.increment.assert_any_call(ACH_LANDLUBBER, 1, [])
    achievement_service.increment.assert_any_call(ACH_SEAMAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_ADMIRAL_OF_THE_FLEET, 1, [])
    assert len(achievement_service.mock_calls) == 3


def test_category_stats_won_more_naval_and_one_experimental(game_stats_service, player, achievement_service, unit_stats):
    unit_stats['air']['built'] = 2
    unit_stats['land']['built'] = 1
    unit_stats['naval']['built'] = 3
    unit_stats['experimental']['built'] = 1

    game_stats_service._category_stats(unit_stats, True, [], [])

    achievement_service.increment.assert_any_call(ACH_LANDLUBBER, 1, [])
    achievement_service.increment.assert_any_call(ACH_SEAMAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_ADMIRAL_OF_THE_FLEET, 1, [])
    achievement_service.increment.assert_any_call(ACH_DR_EVIL, 1, [])

    assert len(achievement_service.mock_calls) == 4


def test_category_stats_won_more_naval_and_three_experimentals(game_stats_service, player, achievement_service, unit_stats):
    unit_stats['air']['built'] = 2
    unit_stats['land']['built'] = 1
    unit_stats['naval']['built'] = 3
    unit_stats['experimental']['built'] = 3

    game_stats_service._category_stats(unit_stats, True, [], [])

    achievement_service.increment.assert_any_call(ACH_LANDLUBBER, 1, [])
    achievement_service.increment.assert_any_call(ACH_SEAMAN, 1, [])
    achievement_service.increment.assert_any_call(ACH_ADMIRAL_OF_THE_FLEET, 1, [])

    achievement_service.increment.assert_any_call(ACH_DR_EVIL, 3, [])
    achievement_service.increment.assert_any_call(ACH_TECHIE, 1, [])
    achievement_service.increment.assert_any_call(ACH_I_LOVE_BIG_TOYS, 1, [])
    achievement_service.increment.assert_any_call(ACH_EXPERIMENTALIST, 1, [])
    assert len(achievement_service.mock_calls) == 7


def test_faction_played_aeon_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._faction_played(Faction.aeon, True, [], [])

    event_service.record_event.assert_any_call(EVENT_AEON_PLAYS, 1, [])
    event_service.record_event.assert_any_call(EVENT_AEON_WINS, 1, [])
    achievement_service.increment.assert_any_call(ACH_AURORA, 1, [])
    achievement_service.increment.assert_any_call(ACH_BLAZE, 1, [])
    achievement_service.increment.assert_any_call(ACH_SERENITY, 1, [])
    assert len(event_service.mock_calls) == 2
    assert len(achievement_service.mock_calls) == 3


def test_faction_played_aeon_died(game_stats_service, player, event_service):
    game_stats_service._faction_played(Faction.aeon, False, [], [])

    event_service.record_event.assert_called_once_with(EVENT_AEON_PLAYS, 1, [])
    assert len(event_service.mock_calls) == 1


def test_faction_played_cybran_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._faction_played(Faction.cybran, True, [], [])

    event_service.record_event.assert_any_call(EVENT_CYBRAN_PLAYS, 1, [])
    event_service.record_event.assert_any_call(EVENT_CYBRAN_WINS, 1, [])
    achievement_service.increment.assert_any_call(ACH_MANTIS, 1, [])
    achievement_service.increment.assert_any_call(ACH_WAGNER, 1, [])
    achievement_service.increment.assert_any_call(ACH_TREBUCHET, 1, [])
    assert len(event_service.mock_calls) == 2
    assert len(achievement_service.mock_calls) == 3


def test_faction_played_cybran_died(game_stats_service, player, event_service):
    game_stats_service._faction_played(Faction.cybran, False, [], [])

    event_service.record_event.assert_called_once_with(EVENT_CYBRAN_PLAYS, 1, [])
    assert len(event_service.mock_calls) == 1


def test_faction_played_uef_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._faction_played(Faction.uef, True, [], [])

    event_service.record_event.assert_any_call(EVENT_UEF_PLAYS, 1, [])
    event_service.record_event.assert_any_call(EVENT_UEF_WINS, 1, [])
    achievement_service.increment.assert_any_call(ACH_MA12_STRIKER, 1, [])
    achievement_service.increment.assert_any_call(ACH_RIPTIDE, 1, [])
    achievement_service.increment.assert_any_call(ACH_DEMOLISHER, 1, [])
    assert len(event_service.mock_calls) == 2
    assert len(achievement_service.mock_calls) == 3


def test_faction_played_uef_died(game_stats_service, player, event_service):
    game_stats_service._faction_played(Faction.uef, False, [], [])

    event_service.record_event.assert_called_once_with(EVENT_UEF_PLAYS, 1, [])
    assert len(event_service.mock_calls) == 1


def test_faction_played_seraphim_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._faction_played(Faction.seraphim, True, [], [])

    event_service.record_event.assert_any_call(EVENT_SERAPHIM_PLAYS, 1, [])
    event_service.record_event.assert_any_call(EVENT_SERAPHIM_WINS, 1, [])
    achievement_service.increment.assert_any_call(ACH_THAAM, 1, [])
    achievement_service.increment.assert_any_call(ACH_YENZYNE, 1, [])
    achievement_service.increment.assert_any_call(ACH_SUTHANUS, 1, [])
    assert len(event_service.mock_calls) == 2
    assert len(achievement_service.mock_calls) == 3


def test_faction_played_seraphim_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._faction_played(Faction.seraphim, False, [], [])

    event_service.record_event.assert_called_once_with(EVENT_SERAPHIM_PLAYS, 1, [])
    assert len(event_service.mock_calls) == 1
    assert len(achievement_service.mock_calls) == 0


def test_killed_acus_one_and_survived(game_stats_service, achievement_service, event_service, unit_stats):
    unit_stats['cdr']['kills'] = 1
    game_stats_service._killed_acus(unit_stats, True, [])

    achievement_service.increment.assert_called_once_with(ACH_DONT_MESS_WITH_ME, 1, [])
    assert len(achievement_service.mock_calls) == 1
    assert len(event_service.mock_calls) == 0


def test_killed_acus_three_and_survived(game_stats_service, achievement_service, event_service, unit_stats):
    unit_stats['cdr']['kills'] = 3
    game_stats_service._killed_acus(unit_stats, True, [])

    achievement_service.increment.assert_called_once_with(ACH_DONT_MESS_WITH_ME, 3, [])
    achievement_service.unlock.assert_called_once_with(ACH_HATTRICK, [])
    assert len(achievement_service.mock_calls) == 2
    assert len(event_service.mock_calls) == 0


def test_killed_acus_one_and_died(game_stats_service, player, achievement_service, event_service, unit_stats):
    unit_stats['cdr']['kills'] = 1
    unit_stats['cdr']['lost'] = 1
    game_stats_service._killed_acus(unit_stats, False, [])

    achievement_service.increment.assert_called_once_with(ACH_DONT_MESS_WITH_ME, 1, [])
    assert len(achievement_service.mock_calls) == 1
    assert len(event_service.mock_calls) == 0


def test_built_salvations_one_and_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_salvations(1, False, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_built_salvations_one_and_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_salvations(1, True, [])
    achievement_service.unlock.assert_called_once_with(ACH_RAINMAKER, [])
    assert len(event_service.mock_calls) == 0


def test_built_yolona_oss_one_and_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_yolona_oss(1, False, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_built_yolona_oss_one_and_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_yolona_oss(1, True, [])
    achievement_service.unlock.assert_called_once_with(ACH_NUCLEAR_WAR, [])
    assert len(event_service.mock_calls) == 0


def test_built_paragons_one_and_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_paragons(1, False, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_built_paragons_one_and_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_paragons(1, True, [])
    achievement_service.unlock.assert_called_once_with(ACH_SO_MUCH_RESOURCES, [])
    assert len(event_service.mock_calls) == 0


def test_built_scathis_one_and_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_scathis(1, False, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_built_scathis_one_and_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_scathis(1, True, [])
    achievement_service.unlock.assert_called_once_with(ACH_MAKE_IT_HAIL, [])
    assert len(event_service.mock_calls) == 0


def test_built_mavors_one_and_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_mavors(1, False, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_built_mavors_one_and_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._built_mavors(1, True, [])
    achievement_service.unlock.assert_called_once_with(ACH_I_HAVE_A_CANON, [])
    assert len(event_service.mock_calls) == 0


def test_lowest_acu_health_zero_died(game_stats_service, player, achievement_service, event_service):
    game_stats_service._lowest_acu_health(0, False, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_lowest_acu_health_499_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._lowest_acu_health(499, True, [])
    achievement_service.unlock.assert_called_once_with(ACH_THAT_WAS_CLOSE, [])
    assert len(event_service.mock_calls) == 0


def test_lowest_acu_health_500_survived(game_stats_service, player, achievement_service, event_service):
    game_stats_service._lowest_acu_health(500, True, [])
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0


def test_top_score_7_players(game_stats_service, achievement_service):
    game_stats_service._highscore(True, 7, [])

    assert len(achievement_service.mock_calls) == 0


def test_top_score_8_players(game_stats_service, achievement_service):
    game_stats_service._highscore(True, 8, [])

    achievement_service.unlock.assert_any_call(ACH_TOP_SCORE, [])
    achievement_service.increment.assert_any_call(ACH_UNBEATABLE, 1, [])
    assert len(achievement_service.mock_calls) == 2

async def test_process_game_stats_abort_processing_if_no_army_result(game_stats_service, game, player, achievement_service, event_service):
    with open("tests/data/game_stats_full_example.json", "r") as stats_file:
        stats = stats_file.read()

    game._results = {}

    await game_stats_service.process_game_stats(player, game, stats)
    assert len(achievement_service.mock_calls) == 0
    assert len(event_service.mock_calls) == 0
