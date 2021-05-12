import statistics
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from sortedcontainers import SortedList

from ...config import config
from ...decorators import with_logger
from ..search import CombinedSearch, Game, Match, Search, get_average_rating
from .matchmaker import Matchmaker


class Container:
    def __init__(self, rating_difference, content):
        self.rating = rating_difference
        self.content = content


class UnevenTeamsException(Exception):
    pass


class NotEnoughPlayersException(Exception):
    pass


@with_logger
class TeamMatchMaker(Matchmaker):
    """
    Matchmaker for teams of varied size. Untested for higher than 4v4 but it should work

    Overview of the algorithm:
    1. list all the parties in queue by their average rating.
    2. Take a party and select the neighboring parties alternating between lower
    and higher until you have 8 players. If the next party to select would leave
    you with more than 8 players you skip that party and try the next one.
    3. you now have a list of parties that will be in your potential game. Distribute
     them into two teams.
     Start with the easiest cases: one party makes a full team already or one party
     has n-1 players so you only need to find the best fitting single player.
     If that is not the case perform the karmarkar-karp algorithm to get a good approximation for a partition
    4. add this game to a games list
    5. repeat 2. to 4. for every party.
    6. you now have a list of potential games with minimal rating variation and minimal rating imbalance.
    7. remove all games with match quality below threshold then sort by quality descending
    8. pick the first game from the game list and remove all other games that contain the same players
    9. repeat until the list is empty

    for the future:
    Find combination of potential games that allows for maximal number of games to launch
    Repeat 8. with an increasing amount of top games removed beforehand to get all possible game combinations
    If there is more than one solution, pick the one with highest total game quality
    Optimization: sort by game quality first, abort when you find a solution with
    the full number of theoretically possible games (floor(playersInQueue/(teamSize*2)))
    """

    def find(self, searches: Iterable[Search]) -> List[Match]:
        self._logger.debug("=== starting matching algorithm ===")

        searches = SortedList(searches, key=lambda s: s.average_rating)
        possible_games = set()
        for index, search in enumerate(searches):

            self._logger.debug("building game for %s", repr(search))

            try:
                participants = self._pick_neighboring_players(searches, index)
                match = self.make_teams(participants)
                game = self.calculate_game_quality(match)
                possible_games.add(game)
            except NotEnoughPlayersException:
                self._logger.warning("Couldn't pick enough players for a full game. Skipping this game...")
            except UnevenTeamsException:
                self._logger.warning("Failed to assign even teams. Skipping this game...")

        self._logger.debug("got %i games", len(possible_games))
        for game in possible_games:
            self._logger.debug("game: %s vs %s rating disparity: %i quality: %f",
                               repr(game.match[0]),
                               repr(game.match[1]),
                               game.match[0].cumulated_rating - game.match[1].cumulated_rating,
                               game.quality)

        return self._pick_best_noncolliding_games(list(possible_games))

    def _pick_neighboring_players(self, searches: List[Search], index: int) -> List[Search]:
        """
        Picks searches from the list starting with the search at the given index and then expanding in both directions
        until there are enough players for a full game.
        Raises NotEnoughPlayersException if it can't find enough suitable searches to fill a game.
        """
        participants = []
        i = 0
        number_of_players = 0
        lower = searches[:index]
        lower = iter(lower[::-1])
        higher = iter(searches[index:])

        failed_last_time = False
        while number_of_players < self.team_size * 2:
            candidate = next(lower if i % 2 else higher, None)
            i += 1
            if candidate is None:
                if failed_last_time:
                    raise NotEnoughPlayersException
                else:
                    failed_last_time = True
                    continue
            failed_last_time = False
            if number_of_players + len(candidate.players) <= self.team_size * 2:
                participants.append(candidate)
                number_of_players += len(candidate.players)
        return participants

    def make_teams(self, searches: List[Search]) -> Tuple[Search, Search]:
        """
        Attempts to partition the given searches into two teams of the appropriate team size
        while also trying that both teams have the same cumulated rating.
        Raises UnevenTeamsException if one of the teams doesn't have the right size.
        :param: The searches to partition. The function will alter this list!
        :return: The two teams
        """
        avg = get_average_rating(searches)
        team_target_strength = sum(search.cumulated_rating for search in searches) / 2
        searches_dict = self._searches_by_size(searches)
        team_a = []
        team_b = []

        if searches_dict[self.team_size]:
            search = searches_dict[self.team_size].pop()
            team_a.append(search)
        elif searches_dict[self.team_size - 1]:
            search = searches_dict[self.team_size - 1].pop()
            filler = self._find_most_balanced_filler(avg, search, searches_dict)
            team_a.append(search)
            team_a.append(filler)
        else:
            team_a, searches = self.run_karmarkar_karp_algorithm(searches)
        team_b.extend(search for search in searches if search not in team_a)

        combined_team_a = CombinedSearch(*team_a)
        combined_team_b = CombinedSearch(*team_b)
        self._logger.debug("made teams: Average rating: %s target strength: %s", avg, team_target_strength)
        self._logger.debug("team a: %s cumulated rating: %s average rating: %s",
                           team_a, combined_team_a.cumulated_rating, combined_team_a.average_rating)
        self._logger.debug("team b: %s cumulated rating: %s average rating: %s",
                           team_b, combined_team_b.cumulated_rating, combined_team_b.average_rating)
        if not len(combined_team_a.players) == self.team_size:
            raise UnevenTeamsException
        if not len(combined_team_b.players) == self.team_size:
            raise UnevenTeamsException
        return combined_team_a, combined_team_b

    def run_karmarkar_karp_algorithm(self, searches):
        self._logger.debug("Running Karmarkar-Karp to partition the teams")
        # Further reading: https://en.wikipedia.org/wiki/Largest_differencing_method
        # Karmarkar-Karp works only for positive integers. By adding 5000 to the rating of each player
        # we also strongly incentivise the algorithm to give both teams the same number of players
        containers = SortedList([Container(5000 * len(s.players) + s.cumulated_rating, [s]) for s in searches],
                                key=lambda c: c.rating)

        elem1 = containers.pop()
        elem2 = containers.pop()
        while True:
            #  elem1 is always bigger than elem2
            container = Container(elem1.rating - elem2.rating, [elem1, elem2])
            containers.add(container)
            elem1 = containers.pop()
            try:
                elem2 = containers.pop()
            except IndexError:
                break
        self._logger.debug("Rating disparity: %s", elem1.rating)

        # We now need to open all containers again to get to the searches. A container can hold a single
        # search or two other containers, so we differentiate the two cases by the length of the content array.
        # Because each container represent the difference of the two containing elements they have to go in
        # different teams (The higher one into the team the container is in).
        team_a = []
        team_b = []
        containers_a = []
        containers_b = []
        containers_a.append(elem1.content[0])
        containers_b.append(elem1.content[1])
        while containers_a or containers_b:
            for e in containers_a:
                if len(e.content) == 2:
                    containers_a.append(e.content[0])
                    containers_b.append(e.content[1])
                else:
                    team_a.append(e.content[0])
                containers_a.remove(e)
            for e in containers_b:
                if len(e.content) == 2:
                    containers_b.append(e.content[0])
                    containers_a.append(e.content[1])
                else:
                    team_b.append(e.content[0])
                containers_b.remove(e)
        return team_a, team_b

    def _searches_by_size(self, searches: List[Search]) -> Dict[int, List[Search]]:
        searches_by_size: Dict[int, List[Search]] = defaultdict(list)

        for search in searches:
            size = len(search.players)
            searches_by_size[size].append(search)

        self._logger.debug("participating searches by player size:")
        for i in range(self.team_size, 0, -1):
            self._logger.debug("%i players: %s", i, searches_by_size[i])
        return searches_by_size

    def _find_most_balanced_filler(self, avg, search, searches_dict):
        """
        If we simply fetch the highest/lowest rated single player search we may overshoot our
        goal to get the most balanced teams, so we try them all until we find the one that brings
        us closest to the rating average i.e. balanced teams
        If there is no single player search we have hit a search combination that is impossible to
        separate into two teams e.g. (3, 3, 2) for 4v4
        """
        team_avg = search.average_rating
        if not searches_dict[1]:
            self._logger.warning("given searches are impossible to split in even teams because of party sizes")
            raise UnevenTeamsException
        candidates = SortedList(searches_dict[1], key=lambda s: s.cumulated_rating)

        if avg - team_avg < 0:
            iterator = iter(candidates)
        else:
            iterator = iter(candidates[::-1])
        candidate = next(iterator)
        for item in iterator:
            team_avg = get_average_rating([search, candidate])
            avg_delta = abs(avg - team_avg)
            new_team_avg = get_average_rating([search, item])
            new_avg_delta = abs(avg - new_team_avg)
            self._logger.debug("delta with %s is %s (avg is %s)", [candidate], avg_delta, team_avg)
            self._logger.debug("new delta with %s is %s (avg is %s)", [item], new_avg_delta, new_team_avg)
            if new_avg_delta > avg_delta:
                break
            candidate = item
        self._logger.debug("used %s as filler", [candidate])
        return candidate

    def calculate_game_quality(self, match: Match) -> Game:
        newbie_bonus = 0
        time_bonus = 0
        ratings = []
        for team in match:
            time_bonus += team.failed_matching_attempts * config.TIME_BONUS
            time_bonus = min(time_bonus, config.MAXIMUM_TIME_BONUS)
            newbie_bonus += team.has_newbie() * config.NEWBIE_BONUS
            for search in team.get_original_searches():
                ratings.append(search.average_rating)

        rating_disparity = abs(match[0].cumulated_rating - match[1].cumulated_rating)
        fairness = max((config.MAXIMUM_RATING_IMBALANCE - rating_disparity) / config.MAXIMUM_RATING_IMBALANCE, 0)
        deviation = statistics.pstdev(ratings)
        uniformity = max((config.MAXIMUM_RATING_DEVIATION - deviation) / config.MAXIMUM_RATING_DEVIATION, 0)

        quality = fairness * uniformity + newbie_bonus + time_bonus
        self._logger.debug(
            "bonuses: %s rating disparity: %s -> fairness: %f deviation: %f -> uniformity: %f -> game quality: %f",
            newbie_bonus + time_bonus, rating_disparity, fairness, deviation, uniformity, quality)
        return Game(match, quality)

    def _pick_best_noncolliding_games(self, games: List[Game]) -> List[Match]:
        for game in list(games):
            if game.quality < config.MINIMUM_GAME_QUALITY:
                games.remove(game)
        self._logger.debug("%i games left after removal of games with quality < %s",
                           len(games), config.MINIMUM_GAME_QUALITY)
        games = SortedList(games, key=lambda gme: gme.quality)

        matches: List[Match] = []
        while len(games) > 0:
            g = games.pop()
            matches.append(g.match)
            used_players = set()
            for search in g.match:
                for player in search.players:
                    used_players.add(player)
            self._logger.debug("used players: %s", [p.login for p in used_players])
            for game in list(games):
                for search in game.match:
                    if not set(search.players).isdisjoint(used_players):
                        games.remove(game)
                        self._logger.debug("removed game: %s", game.match)
                        break
        self._logger.debug("chosen games: " + str(matches))
        return matches
