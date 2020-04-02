import json
import time
from collections import namedtuple

import pytest
from asynctest import CoroutineMock

from server.rating import RatingType
from trueskill import Rating
from server.rating_service.rating_service import RatingService
from server.rating_service.game_rater import GameRatingError

from server.games.game import Game, GameState, GameError, ValidityState
from server.games.game_results import GameOutcome
from server.games.custom_game import CustomGame
from server.games.ladder_game import LadderGame
from tests.unit_tests.conftest import (
    add_connected_player,
    add_connected_players,
    make_mock_game_connection,
)

pytestmark = pytest.mark.asyncio

FFA_TEAM = 1


class PersistenceError(Exception):
    """
    Raised when detecting that rating results would not have been persisted.
    """

    pass


@pytest.fixture
async def rating_service(database, player_service):
    mock_service = RatingService(database, player_service)

    mock_service._persist_rating_changes = CoroutineMock()

    mock_ratings = {}

    def set_mock_rating(player_id, rating_type, rating):
        nonlocal mock_ratings
        nonlocal mock_service
        mock_service._logger.debug(
            f"Set mock {rating_type} rating for player {player_id}: {rating}"
        )
        mock_ratings[(player_id, rating_type)] = rating

    def get_mock_rating(*args, **kwargs):
        nonlocal mock_ratings
        nonlocal mock_service
        player_id, rating_type = args
        value = mock_ratings.get((player_id, rating_type), Rating(1500, 500))
        mock_service._logger.debug(
            f"Retrieved mock {rating_type} rating for player {player_id}: {value}"
        )
        return value

    mock_service.set_mock_rating = set_mock_rating
    mock_service._get_player_rating = CoroutineMock(wraps=get_mock_rating)

    await mock_service.initialize()

    yield mock_service

    mock_service.kill()


def get_persisted_results(mock_service):
    PersistedResults = namedtuple(
        "PersistedResults", ["rating_type", "ratings", "outcomes"]
    )
    args = mock_service._persist_rating_changes.await_args
    if args is None:
        return PersistedResults(None, {}, {})

    # TODO why does this need to be args[0]?
    game_id, rating_type, old_ratings, new_ratings, outcomes = args[0]
    return PersistedResults(rating_type, new_ratings, outcomes)


@pytest.yield_fixture
def game(event_loop, database, game_service, game_stats_service):
    game = Game(42, database, game_service, game_stats_service)
    yield game


@pytest.yield_fixture
def custom_game(event_loop, database, game_service, game_stats_service):
    game = CustomGame(42, database, game_service, game_stats_service)
    yield game


@pytest.yield_fixture
def ladder_game(event_loop, database, game_service, game_stats_service):
    game = LadderGame(42, database, game_service, game_stats_service)
    yield game


def add_players_with_rating(player_factory, game, ratings, teams):
    rating_service = game.game_service._rating_service

    players = [
        (
            player_factory(
                f"{i}",
                player_id=i,
                global_rating=rating,
                ladder_rating=rating,
                with_lobby_connection=False,
            ),
            team,
        )
        for i, (rating, team) in enumerate(zip(ratings, teams), 1)
    ]

    game.state = GameState.LOBBY
    add_connected_players(game, [player for player, _ in players])

    for player, team in players:
        rating_service.set_mock_rating(
            player.id, RatingType.GLOBAL, Rating(*player.ratings[RatingType.GLOBAL])
        )
        rating_service.set_mock_rating(
            player.id,
            RatingType.LADDER_1V1,
            Rating(*player.ratings[RatingType.LADDER_1V1]),
        )
        player._mock_team = team
        game.set_player_option(player.id, "Team", player._mock_team)
        player._test_army = player.id - 1
        game.set_player_option(player.id, "Army", player._test_army)

    return players


async def report_results(game, message_list):
    """
    message list of the form 
    List[(reporter_player_object, army_id_to_report_for, outcome_string, score)]
    """
    for player, army_id, outcome_string, score in message_list:
        await game.add_result(player, army_id, outcome_string, score)


async def test_rating_summary_missing_team_raises_game_error(game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    del game._player_options[players.hosting.id]["Team"]
    await game.launch()

    with pytest.raises(GameError):
        game._get_rating_summary(RatingType.GLOBAL)


async def test_rate_game_global_ratings(custom_game, players):
    rating_service = custom_game.game_service._rating_service
    custom_game.state = GameState.LOBBY
    add_connected_players(custom_game, [players.hosting, players.joining])
    custom_game.set_player_option(players.hosting.id, "Team", 2)
    custom_game.set_player_option(players.joining.id, "Team", 3)

    await custom_game.launch()
    await custom_game.add_result(players.hosting.id, 0, "victory", 1)
    await custom_game.add_result(players.joining.id, 1, "defeat", 0)

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(custom_game.game_service._rating_service)
    assert results.rating_type is RatingType.GLOBAL
    assert players.hosting.id in results.ratings
    assert players.joining.id in results.ratings


async def test_rate_game_ladder_ratings(ladder_game, players):
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "victory", 1)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.rating_type is RatingType.LADDER_1V1
    assert players.hosting.id in results.ratings
    assert players.joining.id in results.ratings


async def test_rate_game_rating_balanced_teamgame(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    players = add_players_with_rating(
        player_factory,
        custom_game,
        [Rating(1500, 250), Rating(1700, 120), Rating(1200, 72), Rating(1200, 72)],
        [2, 2, 3, 3],
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if team == 2 else "defeat", 0)
            for player, team in players
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.rating_type is RatingType.GLOBAL
    for player, _ in players:
        assert results.ratings[player.id] != Rating(*player.ratings[RatingType.GLOBAL])


async def test_rate_game_sum_of_scores_edge_case(custom_game, player_factory):
    """
    For certain scores, compute_rating was determining the winner incorrectly,
    see issue <https://github.com/FAForever/server/issues/485>.
    """
    rating_service = custom_game.game_service._rating_service

    win_team = 2
    lose_team = 3
    rating_list = [Rating(1500, 200)] * 8
    team_list = (4 * [lose_team]) + (4 * [win_team])
    score_list = [1, 1, 1, -10, 10, -10, 2]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (
                player,
                player._test_army,
                "victory" if team == win_team else "defeat",
                score,
            )
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.rating_type is RatingType.GLOBAL
    for player, team in players:
        if team == win_team:
            assert results.ratings[player.id] > Rating(
                *player.ratings[RatingType.GLOBAL]
            )
        else:
            assert results.ratings[player.id] < Rating(
                *player.ratings[RatingType.GLOBAL]
            )


async def test_rate_game_only_one_survivor(custom_game, player_factory):
    """
    When a player dies their score is reported as "defeat", but this does not
    necessarily mean they lost the game, if their team mates went on and later
    reported a "victory".
    """
    rating_service = custom_game.game_service._rating_service

    win_team = 2
    lose_team = 3
    rating_list = [Rating(1500, 200)] * 8
    team_list = (4 * [lose_team]) + (4 * [win_team])
    score_list = (7 * [-10]) + [10]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.rating_type is RatingType.GLOBAL
    for player, team in players:
        if team == win_team:
            assert results.ratings[player.id] > Rating(
                *player.ratings[RatingType.GLOBAL]
            )
        else:
            assert results.ratings[player.id] < Rating(
                *player.ratings[RatingType.GLOBAL]
            )


async def test_rate_game_two_player_FFA(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 250), Rating(1700, 120)]
    team_list = [FFA_TEAM, FFA_TEAM]
    score_list = [0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (
                player,
                player._test_army,
                "victory" if player.id == 1 else "defeat",
                score,
            )
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.rating_type is RatingType.GLOBAL
    for player, _ in players:
        assert (
            results.ratings[player.id] > Rating(*player.ratings[RatingType.GLOBAL])
        ) is (player.id == 1)


async def test_rate_game_does_not_rate_multi_team(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 250), Rating(1700, 120), Rating(1200, 72)]
    team_list = [2, 3, 4]
    score_list = [10, 0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_rate_game_does_not_rate_multi_FFA(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 250), Rating(1700, 120), Rating(1200, 72)]
    team_list = [1, 1, 1]
    score_list = [10, 0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_rate_game_does_not_rate_double_win(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 250), Rating(1700, 120)]
    team_list = [2, 3]
    score_list = [10, 10]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_rating_errors_persisted(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 250), Rating(1700, 120)]
    team_list = [2, 3]
    score_list = [10, 10]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    async with rating_service._db.acquire() as conn:
        rows = await conn.execute(
            "SELECT `validity` FROM `game_stats` " "WHERE `id`=%s", (custom_game.id,)
        )
    row = await rows.fetchone()

    assert row[0] == ValidityState.UNKNOWN_RESULT.value


async def test_rate_game_treats_double_defeat_as_draw(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 500), Rating(1500, 500)]
    team_list = [2, 3]
    score_list = [0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    for player, _ in players:
        new_rating = results.ratings[player.id]
        old_rating = Rating(*player.ratings[RatingType.GLOBAL])

        assert results.outcomes[player.id] is GameOutcome.DRAW
        assert (new_rating.mu - old_rating.mu) < 0.1
        assert new_rating.sigma < old_rating.sigma - 10


async def test_compute_rating_works_with_partially_unknown_results(
    custom_game, player_factory
):
    rating_service = custom_game.game_service._rating_service

    win_team = 2
    lose_team = 3
    rating_list = [
        Rating(1500, 250),
        Rating(1700, 120),
        Rating(1200, 72),
        Rating(1200, 72),
    ]
    team_list = [win_team, win_team, lose_team, lose_team]
    score_list = [10, 0, -10, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "unknown", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.rating_type is RatingType.GLOBAL
    for player, team in players:
        if team == win_team:
            assert results.ratings[player.id] > Rating(
                *player.ratings[RatingType.GLOBAL]
            )
        else:
            assert results.ratings[player.id] < Rating(
                *player.ratings[RatingType.GLOBAL]
            )


async def test_rate_game_single_ffa_vs_single_team(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 500), Rating(1500, 500)]
    team_list = [FFA_TEAM, 3]
    score_list = [10, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    for player, _ in players:
        new_rating = results.ratings[player.id]
        old_rating = Rating(*player.ratings[RatingType.GLOBAL])

        assert new_rating != old_rating


async def test_rate_game_single_ffa_vs_team(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 500)] * 3
    team_list = [FFA_TEAM, 3, 3]
    score_list = [10, 0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_dont_rate_partial_ffa_matches(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 500)] * 4
    team_list = [FFA_TEAM, FFA_TEAM, 3, 3]
    score_list = [10, 0, 0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_dont_rate_pure_ffa_matches_with_more_than_two_players(
    custom_game, player_factory
):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 500)] * 3
    team_list = [FFA_TEAM] * 3
    score_list = [10, 0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_dont_rate_threeway_team_matches(custom_game, player_factory):
    rating_service = custom_game.game_service._rating_service

    rating_list = [Rating(1500, 500)] * 3
    team_list = [2, 3, 4]
    score_list = [10, 0, 0]

    players = add_players_with_rating(
        player_factory, custom_game, rating_list, team_list
    )

    await custom_game.launch()

    await report_results(
        custom_game,
        [
            (player, player._test_army, "victory" if score == 10 else "defeat", score)
            for (player, team), score in zip(players, score_list)
        ],
    )

    custom_game.enforce_rating = True
    await custom_game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    assert results.ratings == {}


async def test_single_wrong_report_still_rated_correctly(game: Game, player_factory):
    # based on replay with UID 11255492

    # Mocking out database calls, since not all player IDs exist.
    game.update_game_player_stats = CoroutineMock()

    game.state = GameState.LOBBY

    # Loading log data
    with open("tests/data/uid11255492.log.json", "r") as f:
        log_dict = json.load(f)

    old_rating = 1500
    players = {
        player_id: player_factory(
            login=f"{player_id}",
            player_id=player_id,
            global_rating=Rating(old_rating, 250),
            with_lobby_connection=False,
        )
        for team in log_dict["teams"].values()
        for player_id in team
    }

    add_connected_players(game, list(players.values()))
    for team_id, team_list in log_dict["teams"].items():
        for player_id in team_list:
            game.set_player_option(player_id, "Team", team_id)
            game.set_player_option(player_id, "Army", player_id - 1)
    await game.launch()

    for reporter, reportee, outcome, score in log_dict["results"]:
        await game.add_result(players[reporter], reportee, outcome, score)

    rating_service = game.game_service._rating_service
    await game.rate_game()
    await rating_service._join_rating_queue()

    results = get_persisted_results(rating_service)
    winning_ids = log_dict["teams"][str(log_dict["winning_team"])]
    for player_id, new_rating in results.ratings.items():
        if player_id in winning_ids:
            assert new_rating.mu > old_rating
        else:
            assert new_rating.my < old_rating
