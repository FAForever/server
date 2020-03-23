import pytest

from server.games.game import Game


@pytest.yield_fixture
def game(event_loop, database, game_service, game_stats_service):
    game = Game(42, database, game_service, game_stats_service)
    yield game


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
    await game.add_result(players.hosting.id, 0, "victory", 1)
    await game.add_result(players.joining.id, 1, "defeat", 0)
    game.set_player_option(players.hosting.id, "Team", 2)
    game.set_player_option(players.joining.id, "Team", 3)
    groups = game.compute_rating()
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


async def test_compute_rating_computes_ladder_ratings(game: Game, players):
    game.state = GameState.LOBBY
    players.hosting.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    players.joining.ratings[RatingType.LADDER_1V1] = Rating(1500, 250)
    add_connected_players(game, [players.hosting, players.joining])
    await game.launch()
    await game.add_result(players.hosting.id, 0, "victory", 1)
    await game.add_result(players.joining.id, 1, "defeat", 0)
    game.set_player_option(players.hosting.id, "Team", 1)
    game.set_player_option(players.joining.id, "Team", 1)
    groups = game.compute_rating(rating=RatingType.LADDER_1V1)
    assert players.hosting in groups[0]
    assert players.joining in groups[1]


async def test_compute_rating_balanced_teamgame(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
        (
            player_factory(
                login=f"{i}",
                player_id=i,
                global_rating=rating,
                with_lobby_connection=False,
            ),
            result,
            team,
        )
        for i, (rating, result, team) in enumerate(
            [
                (Rating(1500, 250), 0, 2),
                (Rating(1700, 120), 0, 2),
                (Rating(1200, 72), 0, 3),
                (Rating(1200, 72), 0, 3),
            ],
            1,
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()
    for player, result, team in players:
        await game.add_result(
            player, player.id - 1, "victory" if team == 2 else "defeat", result
        )
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert player in game.players
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


async def test_compute_rating_sum_of_scores_edge_case(game: Game, player_factory):
    """
    For certain scores, compute_rating was determining the winner incorrectly,
    see issue <https://github.com/FAForever/server/issues/485>.
    """
    game.state = GameState.LOBBY
    win_team = 2
    lose_team = 3
    players = [
        (
            player_factory(
                login=f"{i}",
                player_id=i,
                global_rating=rating,
                with_lobby_connection=False,
            ),
            result,
            team,
        )
        for i, (rating, result, team) in enumerate(
            [
                (Rating(1500, 200), 1, lose_team),
                (Rating(1500, 200), 1, lose_team),
                (Rating(1500, 200), 1, lose_team),
                (Rating(1500, 200), -10, lose_team),
                (Rating(1500, 200), 10, win_team),
                (Rating(1500, 200), -10, win_team),
                (Rating(1500, 200), -10, win_team),
                (Rating(1500, 200), 2, win_team),
            ],
            1,
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, team in players:
        outcome = "victory" if team is win_team else "defeat"
        await game.add_result(player, player.id - 1, outcome, result)

    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            old_rating = Rating(*player.ratings[RatingType.GLOBAL])
            if (
                player.id > 4
            ):  # `team` index in result might not coincide with `team` index in players
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
                with_lobby_connection=False,
            ),
            outcome,
            result,
            team,
        )
        for i, (outcome, result, team) in enumerate(
            [
                ("defeat", -10, lose_team),
                ("defeat", -10, lose_team),
                ("defeat", -10, lose_team),
                ("defeat", -10, lose_team),
                ("defeat", -10, win_team),
                ("defeat", -10, win_team),
                ("defeat", -10, win_team),
                ("victory", 10, win_team),
            ],
            1,
        )
    ]
    add_connected_players(game, [player for player, _, _, _ in players])
    for player, _, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
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
        for i, (rating, result, team) in enumerate(
            [(Rating(1500, 250), 0, 1), (Rating(1700, 120), 0, 1)], 1
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = "victory" if player.id == 1 else "defeat"
        await game.add_result(player, player.id - 1, outcome, result)
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            old_rating = Rating(*player.ratings[RatingType.GLOBAL])
            assert (new_rating > old_rating) is (player.id == 1)


async def test_compute_rating_does_not_rate_multi_team(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
        (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
        for i, (rating, result, team) in enumerate(
            [
                (Rating(1500, 250), 10, 2),
                (Rating(1700, 120), 0, 3),
                (Rating(1200, 72), 0, 4),
            ],
            1,
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = "victory" if result == 10 else "defeat"
        await game.add_result(player, player.id - 1, outcome, result)
    with pytest.raises(GameRatingError):
        game.compute_rating()


async def test_compute_rating_does_not_rate_multi_FFA(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
        (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
        for i, (rating, result, team) in enumerate(
            [
                (Rating(1500, 250), 10, 1),
                (Rating(1700, 120), 0, 1),
                (Rating(1200, 72), 0, 1),
            ],
            1,
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = "victory" if result == 10 else "defeat"
        await game.add_result(player, player.id - 1, outcome, result)
    with pytest.raises(GameRatingError):
        game.compute_rating()


async def test_compute_rating_does_not_rate_double_win(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
        (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
        for i, (rating, result, team) in enumerate(
            [(Rating(1500, 250), 10, 2), (Rating(1700, 120), 0, 3)], 1
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, _ in players:
        await game.add_result(player, player.id - 1, "victory", result)
    with pytest.raises(GameRatingError):
        game.compute_rating()


async def test_compute_rating_treats_double_defeat_as_draw(game: Game, player_factory):
    game.state = GameState.LOBBY
    players = [
        (player_factory(login=f"{i}", player_id=i, global_rating=rating), result, team)
        for i, (rating, result, team) in enumerate(
            [(Rating(1500, 250), 10, 2), (Rating(1500, 250), 0, 3)], 1
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, _ in players:
        await game.add_result(player, player.id - 1, "defeat", result)
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
        for i, (rating, result, team) in enumerate(
            [
                (Rating(1500, 250), 10, 2),
                (Rating(1700, 120), 0, 2),
                (Rating(1200, 72), -10, 3),
                (Rating(1200, 72), 0, 3),
            ],
            1,
        )
    ]
    add_connected_players(game, [player for player, _, _ in players])
    for player, _, team in players:
        game.set_player_option(player.id, "Team", team)
        game.set_player_option(player.id, "Army", player.id - 1)
    await game.launch()

    for player, result, _ in players:
        outcome = "victory" if result == 10 else "unknown"
        await game.add_result(player, player.id - 1, outcome, result)
    result = game.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


# From old GameRater tests
def test_compute_rating_of_two_player_ffa_match_if_one_chose_a_team():
    FFA_TEAM = 1
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1], 2: [p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_compute_rating_for_single_ffa_player_vs_a_team():
    FFA_TEAM = 1
    p1, p2, p3 = MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1], 2: [p2, p3]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_compute_rating_of_two_player_ffa_match_if_none_chose_a_team():
    FFA_TEAM = 1
    p1, p2 = MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1, p2]}
    outcome_py_player = {p1: GameOutcome.VICTORY, p2: GameOutcome.DEFEAT}

    rater = GameRater(players_by_team, outcome_py_player)
    result = rater.compute_rating()
    for team in result:
        for player, new_rating in team.items():
            assert new_rating != Rating(*player.ratings[RatingType.GLOBAL])


def test_dont_rate_partial_ffa_matches():
    FFA_TEAM = 1
    p1, p2, p3, p4 = MockPlayer(), MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1, p3], 2: [p2, p4]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
        p4: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater.compute_rating()


def test_dont_rate_pure_ffa_matches_with_more_than_two_players():
    FFA_TEAM = 1
    p1, p2, p3 = MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {FFA_TEAM: [p1, p2, p3]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater.compute_rating()


def test_dont_rate_threeway_team_matches():
    p1, p2, p3 = MockPlayer(), MockPlayer(), MockPlayer()
    players_by_team = {2: [p1], 3: [p2], 4: [p3]}
    outcome_py_player = {
        p1: GameOutcome.VICTORY,
        p2: GameOutcome.DEFEAT,
        p3: GameOutcome.DEFEAT,
    }

    rater = GameRater(players_by_team, outcome_py_player)
    with pytest.raises(GameRatingError):
        rater.compute_rating()
