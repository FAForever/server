from server.players import Player


def game_name(*teams: list[Player]) -> str:
    """
    Generate a game name based on the players.
    """

    return " Vs ".join(_team_name(team) for team in teams)


def _team_name(team: list[Player]) -> str:
    """
    Generate a team name based on the players. If all players are in the
    same clan, use their clan tag, otherwise use the name of the first
    player.
    """
    assert team

    player_1_name = team[0].login

    if len(team) == 1:
        return player_1_name

    clans = {player.clan for player in team}

    if len(clans) == 1:
        name = clans.pop() or player_1_name
    else:
        name = player_1_name

    return f"Team {name}"
