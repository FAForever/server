from typing import NamedTuple

from server.matchmaker.search import Match, Search


class GameCandidate(NamedTuple):
    """
    Holds the participating searches and a quality rating for a potential game
    from the matchmaker. The quality is not the trueskill quality!
    """
    match: Match
    quality: float

    @property
    def all_searches(self) -> set[Search]:
        return set(search for team in self.match for search in team.get_original_searches())

