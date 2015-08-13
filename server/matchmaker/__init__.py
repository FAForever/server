"""
The matchmaker system

Used for keeping track of queues of players wanting to play specific kinds of games, currently
just used for 1v1 ``ladder''.
"""
from .matchmaker_queue import MatchmakerQueue
from .search import Search
