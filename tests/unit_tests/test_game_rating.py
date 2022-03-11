import json
from collections import defaultdict
from typing import Any, NamedTuple, Optional
from unittest import mock

import pytest

from server.games import (
    CustomGame,
    Game,
    GameError,
    GameState,
    LadderGame,
    ValidityState
)
from server.games.game_results import GameOutcome
from server.games.typedefs import TeamRatingSummary
from server.rating import PlayerRatings, Rating, RatingType
from server.rating_service.rating_service import RatingService
from server.rating_service.typedefs import GameRatingSummary
from tests.unit_tests.conftest import add_connected_players

FFA_TEAM = 1


class PersistenceError(Exception):
    """
    Raised when detecting that rating results would not have been persisted.
    """
    pass


class PersistedResults(NamedTuple):
    rating_type: Optional[str]
    ratings: dict[int, Any]
    outcomes: dict[int, Any]


@pytest.fixture
async def rating_service(database, player_service):
    mock_message_queue_service = mock.Mock()
    mock_message_queue_service.publish = mock.AsyncMock()

    mock_service = RatingService(
        database,
        player_service,
        mock_message_queue_service
    )

    mock_service._persist_rating_changes = mock.AsyncMock()
    mock_service._create_initial_ratings = mock.AsyncMock()

    mock_ratings = defaultdict(dict)

    def set_mock_rating(player_id, rating_type, rating):
        nonlocal mock_ratings
        nonlocal mock_service
        mock_service._logger.debug(
            f"Set mock {rating_type} rating for player {player_id}: {rating}"
        )
        mock_ratings[player_id][rating_type] = rating

    def get_mock_ratings(conn, player_ids, **kwargs):
        nonlocal mock_ratings
        nonlocal mock_service
        player_ratings = {
            player_id: PlayerRatings(mock_service.leaderboards, init=False)
            for player_id in player_ids
        }

        for player_id in player_ids:
            ratings = mock_ratings[player_id]
            for rating_type, rating in ratings.items():
                player_ratings[player_id][rating_type] = rating

        mock_service._logger.debug(
            f"Retrieved mock ratings for players {player_ids}: {player_ratings}"
        )
        return player_ratings

    mock_service.set_mock_rating = set_mock_rating
    mock_service._get_all_player_ratings = mock.AsyncMock(wraps=get_mock_ratings)

    await mock_service.initialize()

    yield mock_service

    mock_service.kill()


def get_persisted_results(mock_service) -> list[PersistedResults]:
    args = mock_service._persist_rating_changes.await_args_list

    return [
        PersistedResults(None, {}, {})
        if args is None else
        PersistedResults(rating_type, new_ratings, outcomes)
        for call in args
        for (
            _conn,
            _game_id,
            rating_type,
            _old_ratings,
            new_ratings,
            outcomes
        ) in call[:1]
    ]


def get_published_results_by_player_id(mock_service):
    args = mock_service._message_queue_service.publish.await_args_list

    result = defaultdict(list)

    for call in args:
        message = call[0][2]
        result[message["player_id"]].append(message)

    return result


@pytest.fixture
def game(event_loop, database, game_service, game_stats_service):
    return Game(
        42, database, game_service, game_stats_service, rating_type=RatingType.GLOBAL
    )


@pytest.fixture
def custom_game(event_loop, database, game_service, game_stats_service):
    return CustomGame(42, database, game_service, game_stats_service)


@pytest.fixture
def ladder_game(event_loop, database, game_service, game_stats_service):
    return LadderGame(42, database, game_service, game_stats_service, rating_type=RatingType.LADDER_1V1)


def add_players_with_rating(player_factory, game, ratings, teams):
    rating_service = game.game_service._rating_service

    players = [
        (
            player_factory(
                f"{i}",
                player_id=i,
                global_rating=rating,
                ladder_rating=rating,
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
    Parameter message_list of the form
    list[(reporter_player_object, army_id_to_report_for, outcome_string, score)]
    """
    for player, army_id, outcome_string, score in message_list:
        await game.add_result(player, army_id, outcome_string, score)


async def test_rating_summary_missing_team_raises_game_error(game, players):
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    del game._player_options[players.hosting.id]["Team"]
    await game.launch()

    with pytest.raises(GameError):
        game.get_team_sets()

    with pytest.raises(GameError):
        await game.resolve_game_results()


async def test_resolve_game_fails_if_not_launched(custom_game, players):
    custom_game.state = GameState.LOBBY
    add_connected_players(custom_game, [players.hosting, players.joining])
    custom_game.set_player_option(players.hosting.id, "Team", 2)
    custom_game.set_player_option(players.joining.id, "Team", 3)

    custom_game.enforce_rating = True
    with pytest.raises(GameError):
        await custom_game.resolve_game_results()


async def test_on_game_end_global_ratings_persisted(custom_game, players):
    rating_service = custom_game.game_service._rating_service
    custom_game.state = GameState.LOBBY
    add_connected_players(custom_game, [players.hosting, players.joining])
    custom_game.set_player_option(players.hosting.id, "Team", 2)
    custom_game.set_player_option(players.joining.id, "Team", 3)

    await custom_game.launch()
    await custom_game.add_result(players.hosting.id, 0, "victory", 1)
    await custom_game.add_result(players.joining.id, 1, "defeat", 0)

    custom_game.enforce_rating = True
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(custom_game.game_service._rating_service)
    assert results.rating_type == RatingType.GLOBAL
    assert players.hosting.id in results.ratings
    assert players.joining.id in results.ratings
    assert results.outcomes[players.hosting.id] is GameOutcome.VICTORY
    assert results.outcomes[players.joining.id] is GameOutcome.DEFEAT


async def test_on_game_end_global_ratings_published(custom_game, players):
    rating_service = custom_game.game_service._rating_service
    custom_game.state = GameState.LOBBY
    add_connected_players(custom_game, [players.hosting, players.joining])
    custom_game.set_player_option(players.hosting.id, "Team", 2)
    custom_game.set_player_option(players.joining.id, "Team", 3)

    await custom_game.launch()
    await custom_game.add_result(players.hosting.id, 0, "victory", 1)
    await custom_game.add_result(players.joining.id, 1, "defeat", 0)

    custom_game.enforce_rating = True
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results = get_published_results_by_player_id(
        custom_game.game_service._rating_service
    )
    assert players.hosting.id in results
    assert players.joining.id in results

    host_result, = results[players.hosting.id]
    assert host_result["rating_type"] == RatingType.GLOBAL
    assert "new_rating_mean" in host_result
    assert "new_rating_deviation" in host_result
    assert host_result["outcome"] == GameOutcome.VICTORY.value

    join_result, = results[players.joining.id]
    assert join_result["rating_type"] == RatingType.GLOBAL
    assert "new_rating_mean" in join_result
    assert "new_rating_deviation" in join_result
    assert join_result["outcome"] == GameOutcome.DEFEAT.value


async def test_on_game_end_ladder_ratings_persisted(ladder_game, players):
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "victory", 1)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.on_game_finish()
    await rating_service._join_rating_queue()

    ladder_results, global_results = get_persisted_results(rating_service)
    assert ladder_results.rating_type == RatingType.LADDER_1V1
    assert players.hosting.id in ladder_results.ratings
    assert players.joining.id in ladder_results.ratings
    assert ladder_results.outcomes[players.hosting.id] is GameOutcome.VICTORY
    assert ladder_results.outcomes[players.joining.id] is GameOutcome.DEFEAT

    assert global_results.rating_type == RatingType.GLOBAL
    assert players.hosting.id in global_results.ratings
    assert players.joining.id not in global_results.ratings
    assert global_results.outcomes[players.hosting.id] is GameOutcome.VICTORY


async def test_on_game_end_ladder_ratings_published(ladder_game, players):
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "victory", 1)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.on_game_finish()
    await rating_service._join_rating_queue()

    results = get_published_results_by_player_id(rating_service)
    assert players.hosting.id in results
    assert players.joining.id in results

    host_ladder_result, host_global_result = results[players.hosting.id]
    assert host_ladder_result["rating_type"] == RatingType.LADDER_1V1
    assert "new_rating_mean" in host_ladder_result
    assert "new_rating_deviation" in host_ladder_result
    assert host_ladder_result["outcome"] == GameOutcome.VICTORY.value

    assert host_global_result["rating_type"] == RatingType.GLOBAL
    assert "new_rating_mean" in host_global_result
    assert "new_rating_deviation" in host_global_result
    assert host_global_result["outcome"] == GameOutcome.VICTORY.value

    join_ladder_result, = results[players.joining.id]
    assert join_ladder_result["rating_type"] == RatingType.LADDER_1V1
    assert "new_rating_mean" in join_ladder_result
    assert "new_rating_deviation" in join_ladder_result
    assert join_ladder_result["outcome"] == GameOutcome.DEFEAT.value


async def test_on_game_end_ladder_same_rating_published_as_persisted(
    ladder_game, players
):
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "victory", 1)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.on_game_finish()
    await rating_service._join_rating_queue()

    ladder_results, global_results = get_persisted_results(rating_service)
    persisted = ladder_results.ratings
    persisted_global = global_results.ratings
    published = get_published_results_by_player_id(rating_service)

    host_id = players.hosting.id
    host_ladder_result, host_global_result = published[host_id]
    assert persisted[host_id].mean == host_ladder_result["new_rating_mean"]
    assert persisted[host_id].dev == host_ladder_result["new_rating_deviation"]
    assert persisted_global[host_id].mean == host_global_result["new_rating_mean"]
    assert persisted_global[host_id].dev == host_global_result["new_rating_deviation"]

    join_id = players.joining.id
    join_ladder_result, = published[join_id]
    assert persisted[join_id].mean == join_ladder_result["new_rating_mean"]
    assert persisted[join_id].dev == join_ladder_result["new_rating_deviation"]


async def test_on_game_end_ladder_ratings_without_score_override(
    ladder_game, players, mocker
):
    mocker.patch("server.games.ladder_game.config.LADDER_1V1_OUTCOME_OVERRIDE", False)
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "victory", 0)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.on_game_finish()
    await rating_service._join_rating_queue()

    ladder_results, global_results = get_persisted_results(rating_service)
    assert ladder_results.rating_type == RatingType.LADDER_1V1
    assert players.hosting.id in ladder_results.ratings
    assert players.joining.id in ladder_results.ratings
    assert ladder_results.outcomes[players.hosting.id] is GameOutcome.VICTORY
    assert ladder_results.outcomes[players.joining.id] is GameOutcome.DEFEAT

    assert global_results.rating_type == RatingType.GLOBAL
    assert players.hosting.id in global_results.ratings
    assert players.joining.id not in global_results.ratings
    assert global_results.outcomes[players.hosting.id] is GameOutcome.VICTORY


async def test_on_game_end_ladder_ratings_uses_score_override(
    ladder_game, players, mocker
):
    mocker.patch("server.games.ladder_game.config.LADDER_1V1_OUTCOME_OVERRIDE", True)
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "defeat", 1)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.on_game_finish()
    await rating_service._join_rating_queue()

    ladder_results, global_results = get_persisted_results(rating_service)
    assert ladder_results.rating_type == RatingType.LADDER_1V1
    assert players.hosting.id in ladder_results.ratings
    assert players.joining.id in ladder_results.ratings
    assert ladder_results.outcomes[players.hosting.id] is GameOutcome.VICTORY
    assert ladder_results.outcomes[players.joining.id] is GameOutcome.DEFEAT

    assert global_results.rating_type == RatingType.GLOBAL
    assert players.hosting.id in global_results.ratings
    assert players.joining.id not in global_results.ratings
    assert global_results.outcomes[players.hosting.id] is GameOutcome.VICTORY


async def test_on_game_end_ladder_ratings_score_override_draw(
    ladder_game, players, mocker
):
    mocker.patch("server.games.ladder_game.config.LADDER_1V1_OUTCOME_OVERRIDE", True)
    rating_service = ladder_game.game_service._rating_service

    ladder_game.state = GameState.LOBBY
    add_connected_players(ladder_game, [players.hosting, players.joining])
    ladder_game.set_player_option(players.hosting.id, "Team", 1)
    ladder_game.set_player_option(players.joining.id, "Team", 1)

    await ladder_game.launch()
    await ladder_game.add_result(players.hosting.id, 0, "defeat", 0)
    await ladder_game.add_result(players.joining.id, 1, "defeat", 0)

    await ladder_game.on_game_finish()
    await rating_service._join_rating_queue()

    ladder_results, global_results = get_persisted_results(rating_service)
    assert ladder_results.rating_type == RatingType.LADDER_1V1
    assert players.hosting.id in ladder_results.ratings
    assert players.joining.id in ladder_results.ratings
    assert ladder_results.outcomes[players.hosting.id] is GameOutcome.DRAW
    assert ladder_results.outcomes[players.joining.id] is GameOutcome.DRAW

    assert global_results.rating_type == RatingType.GLOBAL
    assert players.hosting.id in global_results.ratings
    assert players.joining.id in global_results.ratings
    assert global_results.outcomes[players.hosting.id] is GameOutcome.DRAW
    assert global_results.outcomes[players.joining.id] is GameOutcome.DRAW


async def test_on_game_end_rating_type_not_set(game, players):
    game.rating_type = None
    game._logger.exception = mock.Mock()
    rating_service = game.game_service._rating_service
    game.state = GameState.LOBBY
    add_connected_players(game, [players.hosting, players.joining])
    game.set_player_option(players.hosting.id, "Team", 2)
    game.set_player_option(players.joining.id, "Team", 3)

    await game.launch()
    await game.add_result(players.hosting.id, 0, "victory", 1)
    await game.add_result(players.joining.id, 1, "defeat", 0)

    game.enforce_rating = True
    await game.on_game_finish()

    game._logger.exception.assert_not_called()

    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []

    published_results = get_published_results_by_player_id(rating_service)
    assert published_results == {}


async def test_rate_game_balanced_teamgame(custom_game, player_factory):
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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    assert results.rating_type == RatingType.GLOBAL
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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    assert results.rating_type == RatingType.GLOBAL
    for player, team in players:
        if team == win_team:
            assert results.ratings[player.id] > Rating(
                *player.ratings[RatingType.GLOBAL]
            )
            assert results.outcomes[player.id] is GameOutcome.VICTORY
        else:
            assert results.ratings[player.id] < Rating(
                *player.ratings[RatingType.GLOBAL]
            )
            assert results.outcomes[player.id] is GameOutcome.DEFEAT


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    assert results.rating_type == RatingType.GLOBAL
    for player, team in players:
        if team == win_team:
            assert results.outcomes[player.id] is GameOutcome.VICTORY
            assert results.ratings[player.id] > Rating(
                *player.ratings[RatingType.GLOBAL]
            )
        else:
            assert results.outcomes[player.id] is GameOutcome.DEFEAT
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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    assert results.rating_type == RatingType.GLOBAL
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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    async with rating_service._db.acquire() as conn:
        result = await conn.execute(
            "SELECT `validity` FROM `game_stats` WHERE `id`=:id",
            {"id": custom_game.id}
        )
    row = result.fetchone()

    assert row.validity == ValidityState.UNKNOWN_RESULT.value


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    for player, _ in players:
        new_rating = results.ratings[player.id]
        old_rating = Rating(*player.ratings[RatingType.GLOBAL])

        assert results.outcomes[player.id] is GameOutcome.DRAW
        assert (new_rating.mean - old_rating.mean) < 0.1
        assert new_rating.dev < old_rating.dev - 10


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    assert results.rating_type == RatingType.GLOBAL
    for player, team in players:
        if team == win_team:
            assert results.ratings[player.id] > Rating(
                *player.ratings[RatingType.GLOBAL]
            )
            assert results.outcomes[player.id] is GameOutcome.VICTORY
        else:
            assert results.ratings[player.id] < Rating(
                *player.ratings[RatingType.GLOBAL]
            )
            assert results.outcomes[player.id] is GameOutcome.DEFEAT


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


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
    await custom_game.on_game_finish()
    await rating_service._join_rating_queue()

    all_results = get_persisted_results(rating_service)
    assert all_results == []


async def test_single_wrong_report_still_rated_correctly(game: Game, player_factory):
    # based on replay with UID 11255492

    # Mocking out database calls, since not all player IDs exist.
    game.update_game_player_stats = mock.AsyncMock()

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
    await game.on_game_finish()
    await rating_service._join_rating_queue()

    results, = get_persisted_results(rating_service)
    winning_ids = log_dict["teams"][str(log_dict["winning_team"])]
    for player_id, new_rating in results.ratings.items():
        if player_id in winning_ids:
            assert new_rating.mean > old_rating
        else:
            assert new_rating.mean < old_rating


# NOTE: The following test_rating_adjustment_* tests were created by setting up
# the inputs and copying the results to the expected assertions. They exist
# primarily to document the current behaviour and detect bugs in case the
# behaviour changes, however, there is no reason why the rating initialization
# couldn't be changed and the values in these tests updated.
async def do_test_rating_adjustment(
    rating_service,
    player_factory,
    ratings,
    expected_results
):
    team1 = set()
    team2 = set()
    teams = (team1, team2)
    for player_id, ratings in ratings.items():
        for rating_type, rating in ratings.items():
            rating_service.set_mock_rating(player_id, rating_type, rating)
        # Odds on team1, evens on team2
        teams[(player_id + 1) % 2].add(player_id)

    summary = GameRatingSummary(
        game_id=1,
        rating_type=RatingType.LADDER_1V1,
        teams=[
            TeamRatingSummary(GameOutcome.VICTORY, team1, []),
            TeamRatingSummary(GameOutcome.DEFEAT, team2, [])
        ]
    )
    await rating_service._rate(summary)

    results = get_persisted_results(rating_service)

    assert len(results) == len(expected_results)
    for result, expected in zip(results, expected_results):
        assert result.rating_type == expected.rating_type
        assert result.ratings == expected.ratings
        team1_outcomes = {id: GameOutcome.VICTORY for id in team1}
        team2_outcomes = {id: GameOutcome.DEFEAT for id in team2}
        assert result.outcomes == team1_outcomes | team2_outcomes


# These ratings show up a lot because our tests have a lot of new players
NEWBIE_1V1_WINNER = (1766, 429)
NEWBIE_1V1_LOSER = (1235, 429)


async def test_rating_adjustment_1v1_newbies(rating_service, player_factory):
    IGNORED = object()

    # Both players have no ratings yet
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={1: {}, 2: {}},
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    1: pytest.approx(NEWBIE_1V1_WINNER, abs=1),
                    2: pytest.approx(NEWBIE_1V1_LOSER, abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={1: pytest.approx(NEWBIE_1V1_WINNER, abs=1)},
                outcomes=IGNORED
            )
        ]
    )


async def test_rating_adjustment_1v1_ladder_newbies_global_pros(
    rating_service, player_factory
):
    IGNORED = object()

    # Both players have no ladder rating, but high global rating
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {RatingType.GLOBAL: Rating(2000, 75)},
            2: {RatingType.GLOBAL: Rating(1900, 75)},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    1: pytest.approx(NEWBIE_1V1_WINNER, abs=1),
                    2: pytest.approx(NEWBIE_1V1_LOSER, abs=1),
                },
                outcomes=IGNORED
            )
            # No adjustment performed
        ]
    )


async def test_rating_adjustment_1v1_low_ladder_high_global(
    rating_service, player_factory
):
    IGNORED = object()

    # Both players have lower ladder rating than global, but both are below the
    # rating adjustment limit
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {
                RatingType.GLOBAL: Rating(1000, 75),
                RatingType.LADDER_1V1: Rating(900, 125)
            },
            2: {
                RatingType.GLOBAL: Rating(900, 75),
                RatingType.LADDER_1V1: Rating(700, 125)
            },
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    1: pytest.approx((923, 122), abs=1),
                    2: pytest.approx((677, 122), abs=1),
                },
                outcomes=IGNORED
            )
            # No adjustment performed
        ]
    )


async def test_rating_adjustment_1v1_ladder_pros_global_newbies(
    rating_service, player_factory
):
    IGNORED = object()

    # Both players have high ladder rating but no global rating
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {RatingType.LADDER_1V1: Rating(2000, 75)},
            2: {RatingType.LADDER_1V1: Rating(1900, 75)},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    1: pytest.approx((2011, 75), abs=1),
                    2: pytest.approx((1889, 75), abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={
                    1: pytest.approx((2038, 348), abs=1),
                    2: pytest.approx((1340, 419), abs=1),
                },
                outcomes=IGNORED
            )
        ]
    )


async def test_rating_adjustment_1v1_ladder_pros_global_mixed(
    rating_service, player_factory
):
    IGNORED = object()

    expected_results = [
        PersistedResults(
            rating_type=RatingType.LADDER_1V1,
            ratings={
                1: pytest.approx((2011, 75), abs=1),
                2: pytest.approx((1889, 75), abs=1),
            },
            outcomes=IGNORED
        ),
        PersistedResults(
            rating_type=RatingType.GLOBAL,
            ratings={
                1: pytest.approx((1373, 208), abs=1),
            },
            outcomes=IGNORED
        )
    ]

    # Both players have high ladder rating, one has low global, the other has
    # high global.
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {
                RatingType.LADDER_1V1: Rating(2000, 75),
                RatingType.GLOBAL: Rating(1000, 250),
            },
            2: {
                RatingType.LADDER_1V1: Rating(1900, 75),
                RatingType.GLOBAL: Rating(2100, 75),
            }
        },
        expected_results=expected_results
    )

    # Same as above but player 2's global rating is a bit lower. This should
    # not have an effect on the rating adjustment.
    rating_service._persist_rating_changes.reset_mock()
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {
                RatingType.LADDER_1V1: Rating(2000, 75),
                RatingType.GLOBAL: Rating(1000, 250),
            },
            2: {
                RatingType.LADDER_1V1: Rating(1900, 75),
                RatingType.GLOBAL: Rating(1700, 75),
            }
        },
        expected_results=expected_results
    )


async def test_rating_adjustment_1v1_ladder_pro_vs_global_pro(
    rating_service, player_factory
):
    IGNORED = object()

    # One player has high ladder rating the other has high global
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {RatingType.LADDER_1V1: Rating(2000, 75)},
            2: {RatingType.GLOBAL: Rating(1900, 75)},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    1: pytest.approx((2003, 75), abs=1),
                    2: pytest.approx((1340, 419), abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={
                    1: pytest.approx(NEWBIE_1V1_WINNER, abs=1),
                },
                outcomes=IGNORED
            )
        ]
    )


async def test_rating_adjustment_2v2_newbies(rating_service, player_factory):
    IGNORED = object()

    # All players have no ratings yet
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {}, 3: {},
            2: {}, 4: {},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    # Team 1
                    1: pytest.approx((1688, 466), abs=1),
                    3: pytest.approx((1688, 466), abs=1),
                    # Team 2
                    2: pytest.approx((1312, 466), abs=1),
                    4: pytest.approx((1312, 466), abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={
                    1: pytest.approx((1688, 466), abs=1),
                    3: pytest.approx((1688, 466), abs=1),
                },
                outcomes=IGNORED
            )
        ]
    )


async def test_rating_adjustment_2v2_ladder_newbies_global_joes(
    rating_service,
    player_factory
):
    IGNORED = object()

    # All players have no ladder ratings yet, but some have global
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {RatingType.GLOBAL: Rating(1000, 150)}, 3: {},
            2: {RatingType.GLOBAL: Rating(900, 150)}, 4: {},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    # Team 1
                    1: pytest.approx((1688, 466), abs=1),
                    3: pytest.approx((1688, 466), abs=1),
                    # Team 2
                    2: pytest.approx((1312, 466), abs=1),
                    4: pytest.approx((1312, 466), abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={
                    3: pytest.approx((1688, 466), abs=1),
                },
                outcomes=IGNORED
            )
        ]
    )


async def test_rating_adjustment_3v3_newbies(rating_service, player_factory):
    IGNORED = object()

    # All players have no ratings yet
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {}, 3: {}, 5: {},
            2: {}, 4: {}, 6: {},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    # Team 1
                    1: pytest.approx((1653, 478), abs=1),
                    3: pytest.approx((1653, 478), abs=1),
                    5: pytest.approx((1653, 478), abs=1),
                    # Team 2
                    2: pytest.approx((1347, 478), abs=1),
                    4: pytest.approx((1347, 478), abs=1),
                    6: pytest.approx((1347, 478), abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={
                    1: pytest.approx((1653, 478), abs=1),
                    3: pytest.approx((1653, 478), abs=1),
                    5: pytest.approx((1653, 478), abs=1),
                },
                outcomes=IGNORED
            )
        ]
    )


async def test_rating_adjustment_3v3_ladder_newbies_global_joes(
    rating_service,
    player_factory
):
    IGNORED = object()

    # All players have no ladder ratings yet, but some have global
    await do_test_rating_adjustment(
        rating_service,
        player_factory,
        ratings={
            1: {RatingType.GLOBAL: Rating(1000, 150)}, 3: {}, 5: {},
            2: {RatingType.GLOBAL: Rating(1100, 150)}, 4: {}, 6: {},
        },
        expected_results=[
            PersistedResults(
                rating_type=RatingType.LADDER_1V1,
                ratings={
                    # Team 1
                    1: pytest.approx((1653, 478), abs=1),
                    3: pytest.approx((1653, 478), abs=1),
                    5: pytest.approx((1653, 478), abs=1),
                    # Team 2
                    2: pytest.approx((1347, 478), abs=1),
                    4: pytest.approx((1347, 478), abs=1),
                    6: pytest.approx((1347, 478), abs=1),
                },
                outcomes=IGNORED
            ),
            PersistedResults(
                rating_type=RatingType.GLOBAL,
                ratings={
                    3: pytest.approx((1653, 478), abs=1),
                    5: pytest.approx((1653, 478), abs=1),
                },
                outcomes=IGNORED
            )
        ]
    )
