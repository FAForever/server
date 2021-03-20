from typing import Iterable, List

from ...decorators import with_logger
from ..search import Match, Search


@with_logger
class Matchmaker(object):
    def __init__(self, team_size: int):
        self.team_size = team_size

    def find(self, searches: Iterable[Search]) -> List[Match]:
        raise NotImplementedError(
            "Matchmaker.find should be implemented by concrete subclasses"
        )
