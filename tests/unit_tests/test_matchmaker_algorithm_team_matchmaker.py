import logging
import pytest

from server import config
from server.matchmaker import Search, algorithm, CombinedSearch


@pytest.fixture(scope="module")
def player_factory(player_factory):
    player_id_counter = 0

    def make(
        mean: int = 1500,
        deviation: int = 500,
        ladder_games: int = config.NEWBIE_MIN_GAMES+1,
        name=None
    ):
        nonlocal player_id_counter
        """Make a player with the given ratings"""
        player = player_factory(
            ladder_rating=(mean, deviation),
            ladder_games=ladder_games,
            login=name,
            lobby_connection_spec=None,
            player_id=player_id_counter
        )
        player_id_counter += 1
        return player
    return make


def make_searches(ratings, player_factory):
    searches = []
    for i, r in enumerate(ratings):
        searches.append(Search([player_factory(r + 300, 100, name=f"p{i}")]))
    return searches


def test_new_matchmaker_performance(player_factory, bench, caplog):
    # Disable debug logging for performance
    caplog.set_level(logging.INFO)
    NUM_SEARCHES = 200

    searches = [Search([player_factory(1500, 500, ladder_games=1)]) for _ in range(NUM_SEARCHES)]

    with bench:
        algorithm.TeamMatchMaker().find(searches)

    assert bench.elapsed() < 0.5


def test_new_matchmaker_algorithm(player_factory):
    s = make_searches(
        [1251, 1116, 1038, 1332, 1271, 1142, 1045, 1347, 1359, 1348, 1227, 1118, 1058, 1338, 1271, 1137, 1025],
        player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    c4 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)
    s.append(c4)

    matches = algorithm.TeamMatchMaker().find(s)

    assert len(matches) == 2
    for match in matches:
        assert algorithm.TeamMatchMaker().calculate_game_quality(match).quality > config.MINIMUM_GAME_QUALITY
        for team in match:
            assert len(team.players) == algorithm.TeamMatchMaker().team_size


def test_new_matchmaker_algorithm_2(player_factory):
    s = make_searches(
        [227, 1531, 1628, 1722, 1415, 1146, 937, 1028, 1315, 1236, 1125, 1252, 1185, 1333, 1263, 1184, 1037],
        player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    c4 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)
    s.append(c4)

    matches = algorithm.TeamMatchMaker().find(s)

    assert len(matches) == 1
    for match in matches:
        assert algorithm.TeamMatchMaker().calculate_game_quality(match).quality > config.MINIMUM_GAME_QUALITY
        for team in match:
            assert len(team.players) == algorithm.TeamMatchMaker().team_size


def test_make_teams_new(player_factory):
    s = make_searches([910, 1030, 1170, 1430, 1700, 1650, 1490, 520], player_factory)

    team_a = CombinedSearch(*[s[0], s[1], s[3], s[5]])
    team_b = CombinedSearch(*[s[2], s[4], s[6], s[7]])

    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    # By converting to a set we don't have to worry about order
    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulated_rating - teams[1].cumulated_rating) < 150


def test_make_teams_new_2(player_factory):
    s = make_searches([1310, 620, 1230, 1070, 1180, 1090, 800, 1060], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)

    team_a = CombinedSearch(*[c1, s[2]])
    team_b = CombinedSearch(*[c2, s[0], s[1]])
    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulated_rating - teams[1].cumulated_rating) < 50


def test_make_teams_new_3(player_factory):
    s = make_searches([925, 1084, 1015, 1094, 1403, 1526, 1637, 1718], player_factory)

    team_a = CombinedSearch(*[s[1], s[2], s[4], s[7]])
    team_b = CombinedSearch(*[s[0], s[3], s[5], s[6]])
    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulated_rating - teams[1].cumulated_rating) < 50


def test_make_teams_new_4(player_factory):
    s = make_searches([925, 1084, 1015, 1526, 1637, 1718, 1094, 1403], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)

    team_a = CombinedSearch(*[s[1], s[4], s[6]])
    team_b = CombinedSearch(*[s[0], s[2], s[3], s[5]])
    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulated_rating - teams[1].cumulated_rating) < 50


def test_make_teams_with_negative_rated_players(player_factory):
    s = make_searches([625, -184, -15, 94, 403, 526, 637, -218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)

    team_a = CombinedSearch(*[s[0], s[1], s[3], s[4]])
    team_b = CombinedSearch(*[s[2], s[5], s[6]])
    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)
    assert abs(teams[0].cumulated_rating - teams[1].cumulated_rating) < 50


def test_make_teams_with_full_sized_search(player_factory):
    s = make_searches([925, 1084, 1015, 1094, 1403, 1526, 1637, 1718], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop(), s.pop()])
    s.append(c1)

    team_a = CombinedSearch(*[c1])
    team_b = CombinedSearch(*[s[0], s[1], s[2], s[3]])
    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)


def test_make_teams_with_almost_full_sized_search(player_factory):
    s = make_searches([1415, 125, 1294, 584, 1303, 1526, 1237, 1218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    s.append(c1)

    team_a = CombinedSearch(*[c1, s[3]])
    team_b = CombinedSearch(*[s[0], s[1], s[2], s[4]])
    teams = algorithm.TeamMatchMaker().make_teams(s, 4)

    assert set(teams[0].players) == set(team_a.players)
    assert set(teams[1].players) == set(team_b.players)


def test_handle_impossible_team_splits(player_factory):
    s = make_searches([1415, 125, 1294, 584, 1303, 1526, 1237, 1218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)

    with pytest.raises(AssertionError):
        algorithm.TeamMatchMaker().make_teams(s, 4)


def test_ignore_impossible_team_splits(player_factory):
    s = make_searches([1415, 125, 1294, 584, 1303, 1526, 1237, 1218], player_factory)
    c1 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c2 = CombinedSearch(*[s.pop(), s.pop(), s.pop()])
    c3 = CombinedSearch(*[s.pop(), s.pop()])
    s.append(c1)
    s.append(c2)
    s.append(c3)

    matches = algorithm.TeamMatchMaker().find(s)

    assert len(matches) == 0


def test_game_quality(player_factory):
    s = make_searches([100, 100, 100, 100, 100, 100, 100, 100], player_factory)
    team_a = CombinedSearch(*[s[0], s[1], s[2], s[3]])
    team_b = CombinedSearch(*[s[4], s[5], s[6], s[7]])
    game = algorithm.TeamMatchMaker().calculate_game_quality((team_a, team_b))

    assert game.quality == 1.0


def test_game_quality_2(player_factory):
    s = make_searches([100, 100, 400, 400, 400, 400, 100, 100], player_factory)
    team_a = CombinedSearch(*[s[0], s[1], s[2], s[3]])
    team_b = CombinedSearch(*[s[4], s[5], s[6], s[7]])
    game = algorithm.TeamMatchMaker().calculate_game_quality((team_a, team_b))

    assert game.quality == 0.5


def test_game_quality_3(player_factory):
    s = make_searches([100, 100, 4000, 4000, 4000, 4000, 100, 100], player_factory)
    team_a = CombinedSearch(*[s[0], s[1], s[2], s[3]])
    team_b = CombinedSearch(*[s[4], s[5], s[6], s[7]])
    game = algorithm.TeamMatchMaker().calculate_game_quality((team_a, team_b))

    assert game.quality == 0.0
