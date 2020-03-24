import logging
import time
from typing import Any, List, Tuple
from unittest import mock

import pytest
from asynctest import CoroutineMock
from server.gameconnection import GameConnection, GameConnectionState
from server.games import CoopGame, CustomGame
from server.games.game import (
    Game, GameError, GameState, ValidityState, Victory, VisibilityState
)
from server.games.game_rater import GameRatingError
from server.games.game_results import GameOutcome
from server.rating import RatingType
from tests.unit_tests.conftest import (
    add_connected_player, add_connected_players, make_mock_game_connection
)
from tests.utils import fast_forward
from trueskill import Rating

pytestmark = pytest.mark.asyncio


@pytest.yield_fixture
def game(event_loop, database, game_service, game_stats_service):
    game = Game(42, database, game_service, game_stats_service)
    yield game


@pytest.yield_fixture
def coop_game(event_loop, database, game_service, game_stats_service):
    game = CoopGame(42, database, game_service, game_stats_service)
    yield game


@pytest.yield_fixture
def custom_game(event_loop, database, game_service, game_stats_service):
    game = CustomGame(42, database, game_service, game_stats_service)
    yield game


async def game_player_scores(database, game):
    async with database.acquire() as conn:
        results = await conn.execute(
            "SELECT playerId, score FROM game_player_stats WHERE gameid = %s",
            game.id
        )
        return set(f.as_tuple() for f in await results.fetchall())


async def test_initialization(game: Game):
    assert game.state is GameState.INITIALIZING
    assert game.enforce_rating is False


async def test_instance_logging(database, game_stats_service):
    logger = logging.getLogger('{}.5'.format(Game.__qualname__))
    logger.debug = mock.Mock()
    mock_parent = mock.Mock()
    game = Game(5, database, mock_parent, game_stats_service)
    logger.debug.assert_called_with("%s created", game)


async def test_validate_game_settings(game: Game, game_add_players):
    settings = [
        ('Victory', Victory.SANDBOX, ValidityState.WRONG_VICTORY_CONDITION),
        ('FogOfWar', 'none', ValidityState.NO_FOG_OF_WAR),
        ('CheatsEnabled', 'true', ValidityState.CHEATS_ENABLED),
        ('PrebuiltUnits', 'On', ValidityState.PREBUILT_ENABLED),
        ('NoRushOption', 20, ValidityState.NORUSH_ENABLED),
        ('RestrictedCategories', 1, ValidityState.BAD_UNIT_RESTRICTIONS),
        ('TeamLock', 'unlocked', ValidityState.UNLOCKED_TEAMS)
    ]

    game.state = GameState.LOBBY
    game_add_players(game, 2)

    await check_game_settings(game, settings)

    game.validity = ValidityState.VALID
    await game.validate_game_settings()
    assert game.validity is ValidityState.VALID


async def test_validate_game_settings_coop(coop_game: Game):
    settings = [
        (
            'Victory', Victory.DEMORALIZATION,
            ValidityState.WRONG_VICTORY_CONDITION
        ),
        ('TeamSpawn', 'open', ValidityState.SPAWN_NOT_FIXED),
        ('RevealedCivilians', 'Yes', ValidityState.CIVILIANS_REVEALED),
        ('Difficulty', 1, ValidityState.WRONG_DIFFICULTY),
        ('Expansion', 0, ValidityState.EXPANSION_DISABLED),
    ]

    await check_game_settings(coop_game, settings)

    coop_game.validity = ValidityState.VALID
    await coop_game.validate_game_settings()
    assert coop_game.validity is ValidityState.VALID


async def check_game_settings(
    game: Game, settings: List[Tuple[str, Any, ValidityState]]
):
    for key, value, expected in settings:
        old = game.gameOptions.get(key)
        game.gameOptions[key] = value
        await game.validate_game_settings()
        assert game.validity is expected
        game.gameOptions[key] = old


async def test_add_result_unknown(game, game_add_players):
    game.state = GameState.LOBBY
    players = game_add_players(game, 5, team=1)
    await game.launch()
    await game.add_result(0, 1, 'something invalid', 5)
    assert game.get_player_outcome(players[0]) is GameOutcome.UNKNOWN


async def test_ffa_not_rated(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 5, team=1)
    await game.launch()
    await game.add_result(0, 1, 'victory', 5)
    game.launched_at = time.time() - 60 * 20    # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.FFA_NOT_RANKED


async def test_two_player_ffa_is_rated(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=1)
    await game.launch()
    await game.add_result(0, 1, 'victory', 5)
    game.launched_at = time.time() - 60 * 20    # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.VALID


async def test_multi_team_not_rated(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=2)
    game_add_players(game, 2, team=3)
    game_add_players(game, 2, team=4)
    await game.launch()
    await game.add_result(0, 1, 'victory', 5)
    game.launched_at = time.time() - 60 * 20    # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.MULTI_TEAM


async def test_has_ai_players_not_rated(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=2)
    game_add_players(game, 2, team=3)
    game.AIs = {
        'IA Tech': {
            'Faction': 5,
            'Color': 1,
            'Team': 2,
            'StartSpot': 2
        },
        'Oum-Ashavoh (IA Tech)': {
            'Army': 3
        }
    }
    await game.launch()
    await game.add_result(0, 1, 'victory', 5)
    game.launched_at = time.time() - 60 * 20    # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.HAS_AI_PLAYERS


async def test_uneven_teams_not_rated(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=2)
    game_add_players(game, 3, team=3)
    await game.launch()
    await game.add_result(0, 1, 'victory', 5)
    game.launched_at = time.time() - 60 * 20    # seconds
    await game.on_game_end()
    assert game.validity == ValidityState.UNEVEN_TEAMS_NOT_RANKED


async def test_single_team_not_rated(game, game_add_players):
    n_players = 4
    game.state = GameState.LOBBY
    game_add_players(game, n_players, team=2)
    await game.launch()
    game.launched_at = time.time() - 60 * 20
    for i in range(n_players):
        await game.add_result(0, i + 1, 'victory', 5)
    await game.on_game_end()
    assert game.validity is ValidityState.UNEVEN_TEAMS_NOT_RANKED


async def test_set_player_option(game, players, mock_game_connection):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    assert game.players == {players.hosting}
    game.set_player_option(players.hosting.id, 'Team', 1)
    assert game.get_player_option(players.hosting.id, 'Team') == 1
    assert game.teams == {1}
    game.set_player_option(players.hosting.id, 'StartSpot', 1)
    game.get_player_option(players.hosting.id, 'StartSpot') == 1


async def test_invalid_get_player_option_key(game: Game, players):
    assert game.get_player_option(players.hosting.id, -1) is None


async def test_add_game_connection(game: Game, players, mock_game_connection):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    assert players.hosting in game.players


async def test_add_game_connection_throws_if_not_connected_to_host(
    game: Game, players, mock_game_connection
):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.INITIALIZED
    with pytest.raises(GameError):
        game.add_game_connection(mock_game_connection)

    assert players.hosting not in game.players


async def test_add_game_connection_throws_if_not_lobby_state(
    game: Game, players, mock_game_connection
):
    game.state = GameState.INITIALIZING
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    with pytest.raises(GameError):
        game.add_game_connection(mock_game_connection)

    assert players.hosting not in game.players


async def test_remove_game_connection(
    game: Game, players, mock_game_connection
):
    game.state = GameState.LOBBY
    mock_game_connection.player = players.hosting
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    await game.remove_game_connection(mock_game_connection)
    assert players.hosting not in game.players


async def test_game_end_when_no_more_connections(
    game: Game, mock_game_connection
):
    game.state = GameState.LOBBY

    game.on_game_end = CoroutineMock()
    mock_game_connection.state = GameConnectionState.CONNECTED_TO_HOST
    game.add_game_connection(mock_game_connection)
    await game.remove_game_connection(mock_game_connection)

    game.on_game_end.assert_any_call()


async def test_game_sim_ends_when_no_more_connections(game: Game, players):
    game.state = GameState.LOBBY
    host_conn = add_connected_player(game, players.hosting)
    join_conn = add_connected_player(game, players.joining)
    game.host = players.hosting

    await game.launch()

    await game.remove_game_connection(host_conn)
    await game.remove_game_connection(join_conn)
    assert game.ended


async def test_game_sim_ends_when_connections_ended_sim(game: Game, players):
    game.state = GameState.LOBBY
    host_conn = add_connected_player(game, players.hosting)
    join_conn = add_connected_player(game, players.joining)
    game.host = players.hosting

    await game.launch()

    host_conn.finished_sim = True
    join_conn.finished_sim = True
    await game.check_sim_end()
    assert game.ended


@fast_forward(90)
async def test_game_marked_dirty_when_timed_out(game: Game):
    game.state = GameState.INITIALIZING
    await game.timeout_game()
    assert game.state is GameState.ENDED
    assert game in game.game_service.dirty_games


async def test_clear_slot(
    game: Game, mock_game_connection: GameConnection, player_factory
):
    game.state = GameState.LOBBY
    players = [
        player_factory(player_id=1, login='Dostya', global_rating=(1500, 500)),
        player_factory(player_id=2, login='Rhiza', global_rating=(1500, 500))
    ]
    add_connected_players(game, players)
    game.set_ai_option('rush', 'StartSpot', 3)

    game.clear_slot(0)
    game.clear_slot(3)

    assert game.get_player_option(1, 'StartSpot') == -1
    assert game.get_player_option(1, 'Team') == -1
    assert game.get_player_option(1, 'Army') == -1
    assert game.get_player_option(2, 'StartSpot') == 1
    assert 'rush' not in game.AIs


async def test_game_launch_freezes_players(game: Game, players):
    game.state = GameState.LOBBY
    host_conn = add_connected_player(game, players.hosting)
    game.host = players.hosting
    add_connected_player(game, players.joining)

    await game.launch()

    assert game.state is GameState.LIVE
    assert game.players == {players.hosting, players.joining}

    await game.remove_game_connection(host_conn)
    assert game.players == {players.hosting, players.joining}


async def test_game_teams_represents_active_teams(game: Game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 2)
    assert game.teams == {1, 2}


async def test_invalid_army_not_add_result(game: Game, players):
    await game.add_result(players.hosting.id, 99, "win", 10)

    assert 99 not in game._results


async def test_game_ends_in_mutually_agreed_draw(game: Game, game_add_players):
    game.state = GameState.LOBBY
    players = game_add_players(game, 2)

    await game.launch()
    game.launched_at = time.time() - 60 * 60

    await game.add_result(players[0].id, 0, 'mutual_draw', 0)
    await game.add_result(players[1].id, 1, 'mutual_draw', 0)
    await game.on_game_end()

    assert game.validity is ValidityState.MUTUAL_DRAW


async def test_game_not_ends_in_unilatery_agreed_draw(
    game: Game, players, game_add_players
):
    game.state = GameState.LOBBY
    game_add_players(game, 2)

    await game.launch()
    game.launched_at = time.time() - 60 * 60

    await game.add_result(players.hosting.id, 0, 'mutual_draw', 0)
    await game.add_result(players.joining.id, 1, 'victory', 10)
    await game.on_game_end()

    assert game.validity is not ValidityState.MUTUAL_DRAW


async def test_game_is_invalid_due_to_desyncs(game: Game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    game.host = players.hosting

    await game.launch()
    game.desyncs = 30
    await game.on_game_end()

    assert game.validity is ValidityState.TOO_MANY_DESYNCS


async def test_compute_rating_raises_game_error(game: Game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    # add_connected_players sets this, so we need to unset it again
    del game._player_options[players.hosting.id]["Team"]
    game.set_player_option(players.joining.id, "Team", 1)
    await game.launch()

    with pytest.raises(GameError):
        game.compute_rating(rating=RatingType.LADDER_1V1)


async def test_compute_rating_computes_global_ratings(game: Game, players):
    game.state = GameState.LOBBY
    players.hosting.ratings[RatingType.GLOBAL] = Rating(1500, 250)
    players.joining.ratings[RatingType.GLOBAL] = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting.id, 0, 'victory', 1)
    await game.add_result(players.joining.id, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 2)
    game.set_player_option(players.joining.id, 'Team', 3)
    groups = game.compute_rating()
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


async def test_compute_rating_computes_ladder_ratings(game: Game, players):
    game.state = GameState.LOBBY
    players.hosting.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    players.joining.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting.id, 0, 'victory', 1)
    await game.add_result(players.joining.id, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)
    groups = game.compute_rating(rating=RatingType.LADDER_1V1)
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


async def test_compute_rating_balanced_teamgame(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
            (player_factory(
                login=f"{i}",
                player_id=i,
                global_rating=rating,
                with_lobby_connection=False
            ), result, team)
            for i, (rating, result, team) in enumerate([
                (Rating(1500, 250), 0, 2),
                (Rating(1700, 120), 0, 2),
                (Rating(1200, 72), 0, 3),
                (Rating(1200, 72), 0, 3),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()
    for player, result, team in players:
        await game.add_result(
            player, player.id - 1, 'victory' if team == 2 else 'defeat', result
        )
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert player in game.players
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


async def test_compute_rating_sum_of_scores_edge_case(
    game: Game, player_factory
):
    """
    For certain scores, compute_rating was determining the winner incorrectly,
    see issue <https://github.com/FAForever/server/issues/485>.
    """
    game.state = GameState.LOBBY
    win_team = 2
    lose_team = 3
    players = [
            (player_factory(
                login=f"{i}",
                player_id=i,
                global_rating=rating,
                with_lobby_connection=False
            ), result, team)
            for i, (rating, result, team) in enumerate([
                (Rating(1500, 200), 1, lose_team),
                (Rating(1500, 200), 1, lose_team),
                (Rating(1500, 200), 1, lose_team),
                (Rating(1500, 200), -10, lose_team),
                (Rating(1500, 200), 10, win_team),
                (Rating(1500, 200), -10, win_team),
                (Rating(1500, 200), -10, win_team),
                (Rating(1500, 200), 2, win_team),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, team in players:
        outcome = 'victory' if team is win_team else 'defeat'
        await game.add_result(player, player.id - 1, outcome, result)

    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            old_rating = Rating(*player.ratings[RatingType.GLOBAL])
            if player.id > 4:    # `team` index in result might not coincide with `team` index in players
                assert new_rating > old_rating
            else:
                assert new_rating < old_rating


async def test_compute_rating_only_one_surviver(game: Game, player_factory):
    """
    When a player dies their score is reported as "defeat", but this does not
    necessarily mean they lost the game, if their team mates went on and later
    reported a "victory".
    """
    game.state = GameState.LOBBY
    win_team = 2
    lose_team = 3
    players = [
            (
                player_factory(
                    login=f"{i}",
                    player_id=i,
                    global_rating=Rating(1500, 200),
                    with_lobby_connection=False
                ),
                outcome, result, team
            )
            for i, (outcome, result, team) in enumerate([
                ("defeat", -10, lose_team),
                ("defeat", -10, lose_team),
                ("defeat", -10, lose_team),
                ("defeat", -10, lose_team),
                ("defeat", -10, win_team),
                ("defeat", -10, win_team),
                ("defeat", -10, win_team),
                ("victory", 10, win_team),
            ], 1)]
    add_connected_players(game, [player for player, _, _, _ in players])
    for player, _, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, outcome, result, team in players:
        await game.add_result(player, player.id - 1, outcome, result)

    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            old_rating = Rating(*player.ratings[RatingType.GLOBAL])
            # `team` index in result might not coincide with `team` index in players
            if player.id > 4:
                assert new_rating > old_rating
            else:
                assert new_rating < old_rating


async def test_compute_rating_two_player_FFA(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 0, 1),
               (Rating(1700, 120), 0, 1),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = 'victory' if player.id == 1 else 'defeat'
        await game.add_result(player, player.id - 1, outcome, result)
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            old_rating = Rating(*player.ratings[RatingType.GLOBAL])
            assert (new_rating > old_rating) is (player.id == 1)


async def test_compute_rating_does_not_rate_multi_team(
    game: Game, player_factory
):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 10, 2),
               (Rating(1700, 120), 0, 3),
               (Rating(1200, 72), 0, 4),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = 'victory' if result == 10 else 'defeat'
        await game.add_result(player, player.id - 1, outcome, result)
    with pytest.raises(GameRatingError):
        game.compute_rating()


async def test_compute_rating_does_not_rate_multi_FFA(
    game: Game, player_factory
):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 10, 1),
               (Rating(1700, 120), 0, 1),
               (Rating(1200, 72), 0, 1),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = 'victory' if result == 10 else 'defeat'
        await game.add_result(player, player.id - 1, outcome, result)
    with pytest.raises(GameRatingError):
        game.compute_rating()


async def test_compute_rating_does_not_rate_double_win(
    game: Game, player_factory
):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 10, 2),
               (Rating(1700, 120), 0, 3),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, _ in players:
        await game.add_result(player, player.id - 1, 'victory', result)
    with pytest.raises(GameRatingError):
        game.compute_rating()


async def test_compute_rating_treats_double_defeat_as_draw(
    game: Game, player_factory
):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 10, 2),
               (Rating(1500, 250), 0, 3),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, _ in players:
        await game.add_result(player, player.id - 1, 'defeat', result)
    result = game.compute_rating()
    for team in result:
        for _, new_rating in team.items():
            old_rating = Rating(*player.ratings[RatingType.GLOBAL])
            assert new_rating.mu == old_rating.mu
            assert new_rating.sigma < old_rating.sigma


async def test_compute_rating_works_with_partially_unknown_results(
    game: Game, player_factory
):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 10, 2),
               (Rating(1700, 120), 0, 2),
               (Rating(1200, 72), -10, 3),
               (Rating(1200, 72), 0, 3),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = 'victory' if result == 10 else 'unknown'
        await game.add_result(player, player.id - 1, outcome, result)
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


async def test_game_get_player_outcome_ignores_unknown_results(
    game, game_add_players
):
    game.state = GameState.LOBBY
    players = game_add_players(game, 2)

    await game.add_result(0, 0, 'defeat', 0)
    await game.add_result(0, 0, 'score', 0)
    assert game.get_player_outcome(players[0]) is GameOutcome.DEFEAT

    await game.add_result(0, 1, 'score', 0)
    assert game.get_player_outcome(players[1]) is GameOutcome.UNKNOWN


async def test_on_game_end_does_not_call_rate_game_for_single_player(game):
    game.rate_game = CoroutineMock()
    game.state = GameState.LIVE
    game.launched_at = time.time()

    await game.on_game_end()
    assert game.state is GameState.ENDED
    game.rate_game.assert_not_called()


async def test_on_game_end_calls_rate_game_with_two_players(
    game, game_add_players
):
    game.rate_game = CoroutineMock()
    game.state = GameState.LOBBY
    game_add_players(game, 2)

    await game.launch()

    assert len(game.players) == 2
    await game.add_result(0, 1, 'victory', 10)
    await game.add_result(1, 2, 'defeat', -10)

    await game.on_game_end()
    assert game.state is GameState.ENDED
    game.rate_game.assert_any_call()

    assert game.validity is ValidityState.VALID


async def test_name_sanitization(game):
    game.state = GameState.LOBBY
    game.name = game.sanitize_name("卓☻иAâé~<1000")
    try:
        game.name.encode('utf-16-be').decode('ascii')
    except UnicodeDecodeError:
        pass

    assert game.name == "_Aâé~<1000"


async def test_to_dict(game, player_factory):
    game.state = GameState.LOBBY
    players = [
            (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
            for i, (rating, result, team) in enumerate([
               (Rating(1500, 250), 0, 1),
               (Rating(1700, 120), 0, 1),
               (Rating(1200, 72), 0, 2),
               (Rating(1200, 72), 0, 2),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    game.host = players[0][0]
    await game.launch()
    data = game.to_dict()
    expected = {
        "command": "game_info",
        "visibility": VisibilityState.to_string(game.visibility),
        "password_protected": game.password is not None,
        "uid": game.id,
        "title": game.sanitize_name(game.name),
        "state": 'playing',
        "featured_mod": game.game_mode,
        "sim_mods": game.mods,
        "mapname": game.map_folder_name,
        "map_file_path": game.map_file_path,
        "host": game.host.login,
        "num_players": len(game.players),
        "max_players": game.max_players,
        "launched_at": game.launched_at,
        "teams": {
            team: [
                player.login for player in game.players
                if game.get_player_option(player.id, 'Team') == team
            ]
            for team in game.teams
        }
    }
    assert data == expected


async def test_persist_results_not_called_with_one_player(
    game, player_factory
):
    game.persist_results = CoroutineMock()

    game.state = GameState.LOBBY
    players = [
        player_factory(player_id=1, login='Dostya', global_rating=(1500, 500))
    ]
    add_connected_players(game, players)
    await game.launch()
    assert len(game.players) == 1
    await game.add_result(0, 1, 'victory', 5)
    await game.on_game_end()

    game.persist_results.assert_not_called()


async def test_persist_results_not_called_with_no_results(
    game, game_add_players
):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=2)
    game_add_players(game, 2, team=3)
    game.persist_results = CoroutineMock()
    game.launched_at = time.time() - 60 * 20

    await game.launch()
    await game.on_game_end()

    assert len(game.players) == 4
    assert len(game._results) == 0
    assert game.validity is ValidityState.UNKNOWN_RESULT
    game.persist_results.assert_not_called()


async def test_persist_results_called_with_two_players(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2)
    await game.launch()
    assert len(game.players) == 2
    await game.add_result(0, 1, 'victory', 5)
    await game.on_game_end()

    assert game.get_army_score(1) == 5
    assert len(game.players) == 2

    await game.load_results()
    assert game.get_army_score(1) == 5
    for player in game.players:
        if game.get_player_option(player.id, 'Army') == 1:
            assert game.get_player_outcome(player) is GameOutcome.VICTORY
        else:
            assert game.get_player_outcome(player) is GameOutcome.UNKNOWN


async def test_persist_results_called_for_unranked(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2)
    await game.launch()
    game.validity = ValidityState.BAD_UNIT_RESTRICTIONS
    assert len(game.players) == 2
    await game.add_result(0, 1, 'victory', 5)
    await game.on_game_end()

    assert game.get_army_score(1) == 5
    assert len(game.players) == 2
    for player in game.players:
        if game.get_player_option(player.id, 'Army') == 1:
            assert game.get_player_outcome(player) is GameOutcome.VICTORY
        else:
            assert game.get_player_outcome(player) is GameOutcome.UNKNOWN

    await game.load_results()
    assert game.get_army_score(1) == 5
    for player in game.players:
        if game.get_player_option(player.id, 'Army') == 1:
            assert game.get_player_outcome(player) is GameOutcome.VICTORY
        else:
            assert game.get_player_outcome(player) is GameOutcome.UNKNOWN


async def test_get_army_score_conflicting_results_clear_winner(
    game, game_add_players
):
    game.state = GameState.LOBBY
    game_add_players(game, 3, team=2)
    game_add_players(game, 3, team=3)
    await game.launch()

    await game.add_result(0, 0, 'victory', 1000)
    await game.add_result(1, 0, 'victory', 1234)
    await game.add_result(2, 0, 'victory', 1234)
    await game.add_result(3, 1, 'defeat', 100)
    await game.add_result(4, 1, 'defeat', 123)
    await game.add_result(5, 1, 'defeat', 100)

    # Choose the most frequently reported score
    assert game.get_army_score(0) == 1234
    assert game.get_army_score(1) == 100


async def test_get_army_score_conflicting_results_tied(game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=2)
    game_add_players(game, 2, team=3)
    await game.add_result(0, 0, 'victory', 1000)
    await game.add_result(1, 0, 'victory', 1234)
    await game.add_result(2, 1, 'defeat', 100)
    await game.add_result(3, 1, 'defeat', 123)

    # Choose the highest score
    assert game.get_army_score(0) == 1234
    assert game.get_army_score(1) == 123


async def test_equality(game):
    assert game == game
    assert game != Game(5, mock.Mock(), mock.Mock(), mock.Mock())


async def test_hashing(game):
    assert {
        game: 1,
        Game(game.id, mock.Mock(), mock.Mock(), mock.Mock()): 1
    } == {
        game: 1
    }


async def test_report_army_stats_sends_stats_for_defeated_player(
    game: Game, game_add_players
):
    game.state = GameState.LOBBY
    players = game_add_players(game, 2)

    await game.launch()
    await game.add_result(0, 1, 'defeat', -1)

    with open("tests/data/game_stats_simple_win.json", "r") as stats_file:
        stats = stats_file.read()

    await game.report_army_stats(stats)

    game._game_stats_service.process_game_stats.assert_called_once_with(
        players[1], game, stats
    )


async def test_partial_stats_not_affecting_rating_persistence(
    custom_game, event_service, achievement_service, game_add_players
):
    from server.stats.game_stats_service import GameStatsService
    game = custom_game
    game._game_stats_service = GameStatsService(
        event_service, achievement_service
    )
    game.state = GameState.LOBBY
    players = game_add_players(game, 2)
    game.set_player_option(players[0].id, 'Team', 2)
    game.set_player_option(players[1].id, 'Team', 3)
    old_mean = players[0].ratings[RatingType.GLOBAL][0]

    await game.launch()
    game.launched_at = time.time() - 60 * 60
    await game.add_result(0, 0, 'victory', 10)
    await game.add_result(0, 1, 'defeat', -10)
    await game.report_army_stats({'stats': {'Player 1': {}}})
    await game.on_game_end()

    assert game.validity is ValidityState.VALID
    assert players[0].ratings[RatingType.GLOBAL][0] > old_mean


async def test_players_exclude_observers(
    game: Game, game_add_players, player_factory
):
    game.state = GameState.LOBBY
    players = game_add_players(game, 2)

    obs = player_factory(
        player_id=3, login='Zoidberg', global_rating=(1500, 500)
    )

    game.game_service.player_service[obs.id] = obs
    gc = make_mock_game_connection(
        state=GameConnectionState.CONNECTED_TO_HOST, player=obs
    )
    game.set_player_option(obs.id, 'Army', -1)
    game.set_player_option(obs.id, 'StartSpot', -1)
    game.set_player_option(obs.id, 'Team', 0)
    game.set_player_option(obs.id, 'Faction', 0)
    game.set_player_option(obs.id, 'Color', 0)
    game.add_game_connection(gc)
    await game.launch()

    assert game.players == frozenset(players)


async def test_game_outcomes(game: Game, database, players):
    game.state = GameState.LOBBY
    players.hosting.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    players.joining.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting.id, 0, 'victory', 1)
    await game.add_result(players.joining.id, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)

    host_outcome = game.get_player_outcome(players.hosting)
    guest_outcome = game.get_player_outcome(players.joining)
    assert host_outcome is GameOutcome.VICTORY
    assert guest_outcome is GameOutcome.DEFEAT

    default_values_before_end = {(players.hosting.id, 0), (players.joining.id, 0)}
    assert await game_player_scores(database, game) == default_values_before_end

    await game.on_game_end()
    expected_scores = {(players.hosting.id, 1), (players.joining.id, 0)}
    assert await game_player_scores(database, game) == expected_scores


async def test_game_outcomes_no_results(game: Game, database, players):
    game.state = GameState.LOBBY
    players.hosting.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    players.joining.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)

    host_outcome = game.get_player_outcome(players.hosting)
    guest_outcome = game.get_player_outcome(players.joining)
    assert host_outcome is GameOutcome.UNKNOWN
    assert guest_outcome is GameOutcome.UNKNOWN

    await game.on_game_end()
    expected_scores = {(players.hosting.id, 0), (players.joining.id, 0)}
    assert await game_player_scores(database, game) == expected_scores


async def test_game_outcomes_conflicting(game: Game, database, players):
    game.state = GameState.LOBBY
    players.hosting.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    players.joining.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting.id, 0, 'victory', 1)
    await game.add_result(players.joining.id, 1, 'victory', 0)
    await game.add_result(players.hosting.id, 0, 'defeat', 1)
    await game.add_result(players.joining.id, 1, 'defeat', 0)
    game.set_player_option(players.hosting.id, 'Team', 1)
    game.set_player_option(players.joining.id, 'Team', 1)

    host_outcome = game.get_player_outcome(players.hosting)
    guest_outcome = game.get_player_outcome(players.joining)
    assert host_outcome is GameOutcome.CONFLICTING
    assert guest_outcome is GameOutcome.CONFLICTING
    # No guarantees on scores for conflicting results.


async def test_single_wrong_report_still_rated_correctly(game: Game, player_factory):
    # based on replay with UID 11255492

    # Mocking out database calls, since not all player IDs exist.
    game.update_game_player_stats = CoroutineMock()

    game.state = GameState.LOBBY
    players = [
            (player_factory(
                login=f"{i}",
                player_id=i,
                global_rating=rating,
                with_lobby_connection=False
            ), score, team)
            for i, (rating, score, team) in enumerate([
                (Rating(1500, 250), 0, 2),
                (Rating(1500, 250), 0, 2),
                (Rating(1500, 250), 0, 2),
                (Rating(1500, 250), 0, 2),
                (Rating(1500, 250), 0, 2),
                (Rating(1500, 250), 0, 2),
                (Rating(1500, 250), 0, 3),
                (Rating(1500, 250), 0, 3),
                (Rating(1500, 250), 0, 3),
                (Rating(1500, 250), 0, 3),
                (Rating(1500, 250), 0, 3),
                (Rating(1500, 250), 0, 3),
            ], 1)]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, 'Team', team)
        game.set_player_option(player.id, 'Army', player.id - 1)
    await game.launch()

    await game.add_result(players[0][0].id, 1, "defeat", 0)
    await game.add_result(players[3][0].id, 1, "defeat", 0)
    await game.add_result(players[9][0].id, 1, "defeat", 0)
    await game.add_result(players[4][0].id, 1, "defeat", 0)
    await game.add_result(players[7][0].id, 1, "defeat", 0)
    await game.add_result(players[1][0].id, 1, "defeat", 0)
    await game.add_result(players[10][0].id, 1, "defeat", 0)
    await game.add_result(players[2][0].id, 1, "defeat", 0)
    await game.add_result(players[5][0].id, 1, "defeat", 0)
    await game.add_result(players[8][0].id, 1, "defeat", 0)
    await game.add_result(players[6][0].id, 1, "defeat", 0)
    await game.add_result(players[4][0].id, 8, "defeat", 0)
    await game.add_result(players[6][0].id, 8, "defeat", 0)
    await game.add_result(players[9][0].id, 8, "defeat", 0)
    await game.add_result(players[2][0].id, 8, "defeat", 0)
    await game.add_result(players[3][0].id, 8, "defeat", 0)
    await game.add_result(players[0][0].id, 8, "defeat", 0)
    await game.add_result(players[8][0].id, 8, "defeat", 0)
    await game.add_result(players[7][0].id, 8, "defeat", 0)
    await game.add_result(players[5][0].id, 8, "defeat", 0)
    await game.add_result(players[10][0].id, 8, "defeat", 0)
    await game.add_result(players[1][0].id, 8, "defeat", 0)
    await game.add_result(players[4][0].id, 11, "defeat", 0)
    await game.add_result(players[4][0].id, 0, "defeat", 0)
    await game.add_result(players[4][0].id, 2, "defeat", 0)
    await game.add_result(players[4][0].id, 3, "defeat", 0)
    await game.add_result(players[4][0].id, 6, "defeat", 0)
    await game.add_result(players[4][0].id, 4, "defeat", 0)
    await game.add_result(players[4][0].id, 5, "defeat", 0)
    await game.add_result(players[4][0].id, 7, "defeat", 0)
    await game.add_result(players[9][0].id, 7, "defeat", 0)
    await game.add_result(players[6][0].id, 7, "defeat", 0)
    await game.add_result(players[0][0].id, 7, "defeat", 0)
    await game.add_result(players[2][0].id, 7, "defeat", 0)
    await game.add_result(players[10][0].id, 7, "defeat", 0)
    await game.add_result(players[8][0].id, 7, "defeat", 0)
    await game.add_result(players[5][0].id, 7, "defeat", 0)
    await game.add_result(players[7][0].id, 7, "defeat", 0)
    await game.add_result(players[1][0].id, 7, "defeat", 0)
    await game.add_result(players[9][0].id, 3, "defeat", 0)
    await game.add_result(players[0][0].id, 3, "defeat", 0)
    await game.add_result(players[2][0].id, 3, "defeat", 0)
    await game.add_result(players[1][0].id, 3, "defeat", 0)
    await game.add_result(players[7][0].id, 3, "defeat", 0)
    await game.add_result(players[6][0].id, 3, "defeat", 0)
    await game.add_result(players[8][0].id, 3, "defeat", 0)
    await game.add_result(players[10][0].id, 3, "defeat", 0)
    await game.add_result(players[5][0].id, 3, "defeat", 0)
    await game.add_result(players[0][0].id, 3, "defeat", 0)
    await game.add_result(players[9][0].id, 3, "defeat", 0)
    await game.add_result(players[6][0].id, 3, "defeat", 0)
    await game.add_result(players[7][0].id, 3, "defeat", 0)
    await game.add_result(players[8][0].id, 3, "defeat", 0)
    await game.add_result(players[2][0].id, 3, "defeat", 0)
    await game.add_result(players[10][0].id, 3, "defeat", 0)
    await game.add_result(players[1][0].id, 3, "defeat", 0)
    await game.add_result(players[5][0].id, 3, "defeat", 0)
    await game.add_result(players[6][0].id, 9, "defeat", 0)
    await game.add_result(players[7][0].id, 9, "defeat", 0)
    await game.add_result(players[8][0].id, 9, "defeat", 0)
    await game.add_result(players[9][0].id, 9, "defeat", 0)
    await game.add_result(players[2][0].id, 9, "defeat", 0)
    await game.add_result(players[1][0].id, 9, "defeat", 0)
    await game.add_result(players[10][0].id, 9, "defeat", 0)
    await game.add_result(players[0][0].id, 9, "defeat", 0)
    await game.add_result(players[5][0].id, 9, "defeat", 0)
    await game.add_result(players[9][0].id, 0, "defeat", 0)
    await game.add_result(players[6][0].id, 0, "defeat", 0)
    await game.add_result(players[2][0].id, 0, "defeat", 0)
    await game.add_result(players[7][0].id, 0, "defeat", 0)
    await game.add_result(players[8][0].id, 0, "defeat", 0)
    await game.add_result(players[10][0].id, 0, "defeat", 0)
    await game.add_result(players[1][0].id, 0, "defeat", 0)
    await game.add_result(players[5][0].id, 0, "defeat", 0)
    await game.add_result(players[7][0].id, 11, "defeat", 0)
    await game.add_result(players[7][0].id, 6, "defeat", 0)
    await game.add_result(players[8][0].id, 11, "defeat", 0)
    await game.add_result(players[1][0].id, 11, "defeat", 0)
    await game.add_result(players[9][0].id, 11, "defeat", 0)
    await game.add_result(players[6][0].id, 11, "defeat", 0)
    await game.add_result(players[10][0].id, 11, "defeat", 0)
    await game.add_result(players[2][0].id, 11, "defeat", 0)
    await game.add_result(players[6][0].id, 10, "defeat", 0)
    await game.add_result(players[2][0].id, 10, "defeat", 0)
    await game.add_result(players[9][0].id, 10, "defeat", 0)
    await game.add_result(players[1][0].id, 10, "defeat", 0)
    await game.add_result(players[10][0].id, 10, "defeat", 0)
    await game.add_result(players[8][0].id, 10, "defeat", 0)
    await game.add_result(players[2][0].id, 2, "defeat", 0)
    await game.add_result(players[2][0].id, 4, "defeat", 0)
    await game.add_result(players[2][0].id, 5, "defeat", 0)
    await game.add_result(players[2][0].id, 6, "defeat", 0)
    await game.add_result(players[6][0].id, 6, "defeat", 0)
    await game.add_result(players[1][0].id, 6, "defeat", 0)
    await game.add_result(players[9][0].id, 6, "defeat", 0)
    await game.add_result(players[8][0].id, 6, "defeat", 0)
    await game.add_result(players[10][0].id, 6, "defeat", 0)
    await game.add_result(players[1][0].id, 2, "victory", 0)
    await game.add_result(players[6][0].id, 2, "victory", 0)
    await game.add_result(players[6][0].id, 4, "victory", 0)
    await game.add_result(players[6][0].id, 5, "victory", 0)
    await game.add_result(players[1][0].id, 4, "victory", 0)
    await game.add_result(players[1][0].id, 5, "victory", 0)
    await game.add_result(players[8][0].id, 2, "victory", 0)
    await game.add_result(players[9][0].id, 2, "victory", 0)
    await game.add_result(players[9][0].id, 4, "victory", 0)
    await game.add_result(players[9][0].id, 5, "victory", 0)
    await game.add_result(players[8][0].id, 4, "victory", 0)
    await game.add_result(players[8][0].id, 5, "victory", 0)
    await game.add_result(players[10][0].id, 2, "victory", 0)
    await game.add_result(players[10][0].id, 4, "victory", 0)
    await game.add_result(players[10][0].id, 5, "victory", 0)

    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert player in game.players
            player_is_on_winning_team = player.id < 7
            rating_improved = new_rating.mu > 1500
            assert rating_improved is player_is_on_winning_team


async def test_victory_conditions():
    conds = [("demoralization", Victory.DEMORALIZATION),
             ("domination", Victory.DOMINATION),
             ("eradication", Victory.ERADICATION),
             ("sandbox", Victory.SANDBOX)]

    for string_value, enum_value in conds:
        assert Victory.from_gpgnet_string(string_value) == enum_value


async def test_visibility_states():
    states = [("public", VisibilityState.PUBLIC),
              ("friends", VisibilityState.FRIENDS)]

    for string_value, enum_value in states:
        assert (
            VisibilityState.from_string(string_value) == enum_value
            and VisibilityState.to_string(enum_value) == string_value
        )


async def test_is_even(game: Game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 4, team=2)
    game_add_players(game, 4, team=3)

    assert game.is_even


async def test_is_even_no_players(game: Game):
    game.state = GameState.LOBBY

    assert game.is_even


async def test_is_even_single_player(game: Game, game_add_players):
    game.state = GameState.LOBBY
    game_add_players(game, 2, team=2)

    assert not game.is_even


async def test_is_even_ffa(game: Game, game_add_players):
    game.state = GameState.LOBBY
    # Team 1 is the special "-" team
    game_add_players(game, 5, team=1)

    assert game.is_even
