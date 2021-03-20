import itertools
import math
import random
import statistics as stats
from collections import OrderedDict
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

from ...decorators import with_logger
from ..search import CombinedSearch, Match, Search

@with_logger
class Matchmaker(object):
    def __init__(self, team_size: int):
        self.team_size = team_size

    def find(self, searches: Iterable[Search]) -> List[Match]:
        raise NotImplementedError(
            "Matchmaker.find should be implemented by concrete subclasses"
        )
