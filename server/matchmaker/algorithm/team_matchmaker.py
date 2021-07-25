import logging
import statistics
from collections import defaultdict
from typing import Dict, Iterable, List, NamedTuple, Set, Tuple

from sortedcontainers import SortedList

from ...config import config
from ...decorators import with_logger
from ..search import CombinedSearch, Match, Search, get_average_rating
from .matchmaker import Matchmaker
from .stable_marriage import StableMarriageMatchmaker


class GameCandidate(NamedTuple):
    """
    Holds the participating searches and a quality rating for a potential game
    from the matchmaker. The quality is not the trueskill quality!
    """
    match: Match
    quality: float

    @property
    def all_searches(self) -> Set[Search]:
        return set(search for team in self.match for search in team.get_original_searches())


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
    9. repeat 8. until the list is empty
    """
    def find(self, searches: Iterable[Search], team_size: int) -> Tuple[List[Match], List[Search]]:
        if not searches:
            return [], []

        if team_size == 1:
            return StableMarriageMatchmaker().find(searches, 1)

        searches = SortedList(searches, key=lambda s: s.average_rating)
        possible_games = []

        self._logger.debug("========= starting matching algorithm =========")
        self._logger.debug("Searches in queue: %s", list(searches))

        for index, search in enumerate(searches):

            self._logger.debug("building game for %r", search)

            try:
                participants = self.pick_neighboring_players(searches, index, team_size)
                match = self.make_teams(participants, team_size)
                game = self.assign_game_quality(match)
                possible_games.append(game)
            except NotEnoughPlayersException:
                self._logger.warning("Couldn't pick enough players for a full game. Skipping this game...")
            except UnevenTeamsException:
                self._logger.warning("Failed to assign even teams. Skipping this game...")

        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug("got %i games", len(possible_games))
            for game in possible_games:
                self._logger.debug(
                    "%r vs %r rating disparity: %i quality: %f",
                    game.match[0],
                    game.match[1],
                    game.match[0].cumulative_rating - game.match[1].cumulative_rating,
                    game.quality
                )

        matches = self.pick_noncolliding_games(possible_games)
        for match in matches:
            for team in match:
                for search in team.get_original_searches():
                    searches.remove(search)
        return matches, list(searches)

    def pick_neighboring_players(self, searches: List[Search], index: int, team_size: int) -> List[Search]:
        """
        Picks searches from the list starting with the search at the given index and then expanding in both directions
        until there are enough players for a full game.

        # Errors
        May raise `NotEnoughPlayersException` if it can't find enough suitable searches to fill a game.
        """
        # We need to do this in two steps to ensure that index = 0 gives an empty iterator
        lower = searches[:index]
        lower = iter(lower[::-1])
        higher = iter(searches[index+1:])
        pick_lower = True
        candidate = searches[index]
        participants = [candidate]
        number_of_players = len(candidate.players)

        while number_of_players < team_size * 2:
            candidate, prev = next(lower if pick_lower else higher, None), candidate
            pick_lower = not pick_lower
            if candidate is None:
                if prev is None:
                    raise NotEnoughPlayersException()
                continue
            if number_of_players + len(candidate.players) <= team_size * 2:
                participants.append(candidate)
                number_of_players += len(candidate.players)
        return participants

    def make_teams(self, participants: List[Search], team_size: int) -> Tuple[Search, Search]:
        """
        Attempts to partition the given searches into two teams of the appropriate team size
        while also trying that both teams have the same cumulative rating.
        Raises UnevenTeamsException if one of the teams doesn't have the right size.

        # Params
        - `participants`: The searches to partition. The function will alter this list!

        # Return
        The two teams
        """
        if len(participants) < 2:
            raise UnevenTeamsException()

        avg = get_average_rating(participants)
        team_target_strength = sum(search.cumulative_rating for search in participants) / 2
        participants_dict = self._searches_by_size(participants)
        team_a = []
        team_b = []

        if participants_dict[team_size]:
            search = participants_dict[team_size].pop()
            team_a.append(search)
        elif participants_dict[team_size - 1]:
            search = participants_dict[team_size - 1].pop()
            filler = self._find_most_balanced_filler(avg, search, participants_dict[1])
            team_a.append(search)
            team_a.append(filler)
        else:
            team_a, participants = self._run_karmarkar_karp_algorithm(participants)
        team_b.extend(search for search in participants if search not in team_a)

        combined_team_a = CombinedSearch(*team_a)
        combined_team_b = CombinedSearch(*team_b)
        self._logger.debug("made teams: Target cumulative rating: %s average rating: %s", team_target_strength, avg)
        self._logger.debug("team a: %s cumulative rating: %s average rating: %s",
                           team_a, combined_team_a.cumulative_rating, combined_team_a.average_rating)
        self._logger.debug("team b: %s cumulative rating: %s average rating: %s",
                           team_b, combined_team_b.cumulative_rating, combined_team_b.average_rating)
        if not len(combined_team_a.players) == team_size:
            raise UnevenTeamsException()
        if not len(combined_team_b.players) == team_size:
            raise UnevenTeamsException()
        return combined_team_a, combined_team_b

    def _run_karmarkar_karp_algorithm(self, searches: List[Search]) -> Tuple[List[Search], List[Search]]:
        class Container:
            def __init__(self, rating_difference, content):
                self.rating: int = rating_difference
                self.content: List = content

            def holds_containers(self):
                return len(self.content) == 2

        self._logger.debug("Running Karmarkar-Karp to partition the teams")
        # Further reading: https://en.wikipedia.org/wiki/Largest_differencing_method
        # Karmarkar-Karp works only for positive integers. By adding 5000 to the rating of each player
        # we also strongly incentivise the algorithm to give both teams the same number of players
        containers = SortedList(
            [Container(5000 * len(s.players) + s.cumulative_rating, [s]) for s in searches],
            key=lambda c: c.rating
        )

        elem1 = containers.pop()
        elem2 = containers.pop()
        while True:
            # elem1 is always bigger than elem2
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
            if containers_a:
                e = containers_a.pop()
                if e.holds_containers():
                    containers_a.append(e.content[0])
                    containers_b.append(e.content[1])
                else:
                    team_a.append(e.content[0])
            if containers_b:
                e = containers_b.pop()
                if e.holds_containers():
                    containers_b.append(e.content[0])
                    containers_a.append(e.content[1])
                else:
                    team_b.append(e.content[0])
        return team_a, team_b

    def _searches_by_size(self, searches: List[Search]) -> Dict[int, List[Search]]:
        searches_by_size: Dict[int, List[Search]] = defaultdict(list)

        for search in searches:
            searches_by_size[len(search.players)].append(search)

        if self._logger.isEnabledFor(logging.DEBUG):
            max_size = max(searches_by_size.keys())
            self._logger.debug("participating searches by player size:")
            for i in range(1, max_size + 1):
                self._logger.debug("%i players: %s", i, searches_by_size[i])
        return searches_by_size

    def _find_most_balanced_filler(self, avg: int, search: Search, single_player_searches: List[Search]) -> Search:
        """
        If we simply fetch the highest/lowest rated single player search we may overshoot our
        goal to get the most balanced teams, so we try them all to find the one that brings us
        closest to the rating average i.e. balanced teams
        If there is no single player search we have hit a search combination that is impossible to
        separate into two teams e.g. (3, 3, 2) for 4v4
        """
        if not single_player_searches:
            self._logger.warning("given searches are impossible to split in even teams because of party sizes")
            raise UnevenTeamsException()

        candidate = min(
            single_player_searches,
            key=lambda item: abs(avg - get_average_rating([search, item]))
        )
        self._logger.debug("used %s as best filler", [candidate])
        return candidate

    def assign_game_quality(self, match: Match) -> GameCandidate:
        newbie_bonus = 0
        time_bonus = 0
        ratings = []
        for team in match:
            for search in team.get_original_searches():
                ratings.append(search.average_rating)
                search_time_bonus = search.failed_matching_attempts * config.TIME_BONUS * len(search.players)
                time_bonus += min(search_time_bonus, config.MAXIMUM_TIME_BONUS)
                search_newbie_bonus = search.failed_matching_attempts * config.NEWBIE_TIME_BONUS * search.has_newbie()
                newbie_bonus += min(search_newbie_bonus, config.MAXIMUM_NEWBIE_TIME_BONUS)

        rating_disparity = abs(match[0].cumulative_rating - match[1].cumulative_rating)
        fairness = max((config.MAXIMUM_RATING_IMBALANCE - rating_disparity) / config.MAXIMUM_RATING_IMBALANCE, 0)
        deviation = statistics.pstdev(ratings)
        uniformity = max((config.MAXIMUM_RATING_DEVIATION - deviation) / config.MAXIMUM_RATING_DEVIATION, 0)

        quality = fairness * uniformity + newbie_bonus + time_bonus
        self._logger.debug(
            "bonuses: %s rating disparity: %s -> fairness: %f deviation: %f -> uniformity: %f -> game quality: %f",
            newbie_bonus + time_bonus, rating_disparity, fairness, deviation, uniformity, quality)
        return GameCandidate(match, quality)

    def pick_noncolliding_games(self, games: List[GameCandidate]) -> List[Match]:
        """
        This greedily picks all matches with disjoint players, starting with the game with the highest quality.
        This can miss more optimal solutions, but extensive testing showed that over many matchmaker
        iterations there is no benefit to use a more sophisticated algorithm.
        """
        games = [game for game in games if game.quality >= config.MINIMUM_GAME_QUALITY]
        self._logger.debug(
            "%i games left after removal of games with quality < %s", len(games),
            config.MINIMUM_GAME_QUALITY
        )
        games = SortedList(games, key=lambda game: game.quality)

        matches = []
        used_searches = set()
        for game in reversed(games):
            if used_searches.isdisjoint(game.all_searches):
                matches.append(game.match)
                used_searches.update(game.all_searches)
                self._logger.debug("used players: %s", [search for search in used_searches])

        if self._logger.isEnabledFor(logging.DEBUG):
            if matches:
                self._logger.debug("Chosen games:")
            for match in matches:
                self._logger.debug("%r vs %r ", match[0], match[1])
        return matches
