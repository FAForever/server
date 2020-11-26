"""
The matchmaker system

Used for keeping track of queues of players wanting to play specific kinds of
games, currently just used for 1v1 ``ladder``.
"""
from .map_pool import MapPool
from .matchmaker_queue import MatchmakerQueue
from .pop_timer import PopTimer
from .search import CombinedSearch, OnMatchedCallback, Search

__all__ = (
    "CombinedSearch",
    "MapPool",
    "MatchmakerQueue",
    "OnMatchedCallback",
    "PopTimer",
    "Search",
)
