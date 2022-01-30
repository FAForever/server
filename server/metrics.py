"""
Prometheus metric definitions
"""

import sys
from collections import defaultdict
from typing import TypeVar

from prometheus_client import Counter, Gauge, Histogram, Info

info = Info("build", "Information collected on server start")

# ==========
# Matchmaker
# ==========
matches = Gauge("server_matchmaker_queue_matches", "Number of matches made", ["queue"])

match_quality = Histogram(
    "server_matchmaker_queue_quality",
    "Quality of matches made",
    ["queue"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95],
)

unmatched_searches = Gauge(
    "server_matchmaker_queue_unmatched_searches",
    "Number of unmatched searches after queue pop",
    ["queue"],
)

matchmaker_searches = Histogram(
    "server_matchmaker_queue_search_duration_seconds",
    "Time spent searching for matches per search in seconds",
    ["queue", "status"],
    buckets=[30, 60, 120, 180, 240, 300, 600, 1800, 3600],
)

matchmaker_players = Gauge(
    "server_matchmaker_queue_players", "Players in the queue at pop time", ["queue"]
)

matchmaker_queue_pop = Gauge(
    "server_matchmaker_queue_pop_timer_seconds",
    "Queue pop timer duration in seconds",
    ["queue"],
)

# =====
# Users
# =====
user_connections = Gauge(
    "server_user_connections",
    "Number of users currently connected to server",
    ["user_agent", "version"],
)

user_logins = Counter(
    "server_user_logins_total", "Total number of login attempts made", ["status", "method"]
)

user_agent_version = Counter(
    "server_user_agent_version_checks_total",
    "Total number of user agent version checks made",
    ["version"],
)

players_online = Gauge(
    "server_user_online",
    "Number of users currently online as per lobbyconnection.player_service",
)


# ========================
# Connections and Messages
# ========================
server_connections = Counter(
    "server_lobbyconnections_total",
    "Total number of connections to the lobby as per lobbyconnection.on_connection_made",
)

sent_messages = Counter(
    "server_messages_total",
    "Total number of Messages sent",
    ["protocol"]
)

unauth_messages = Counter(
    "server_messages_unauthenticated_total",
    "Total number of unauthenticated messages",
    ["command"],
)

server_broadcasts = Counter(
    "server_broadcasts_total", "Total number of broadcasts"
)

connection_on_message_received = Histogram(
    "server_on_message_received_seconds",
    "Seconds spent in 'connection.on_message_received'",
)

db_exceptions = Counter(
    "db_exceptions_total",
    "Total number of database exceptions when executing queries",
    ["class", "code"]
)


# =====
# Games
# =====
active_games = Gauge(
    "server_game_active_games_total",
    "Number of currently active games. "
    "Includes games in lobby, games currently running, and games that ended "
    "but are still in the game_service.",
    ["game_mode", "game_state"],
)


# ==============
# Rating Service
# ==============
rating_service_backlog = Gauge(
    "server_rating_service_backlog", "Number of games remaining to be rated",
)


# =======
# General
# =======
server_data_len = Gauge(
    "server_data_len", "Length of an object as returned by `len`",
    ["name"],
)
server_data_sizeof = Gauge(
    "server_data_sizeof", "Size of an object in bytes",
    ["name"],
)
server_data_read = Counter(
    "server_data_read",
    "Calls to read operations such as `__getitem__` or `get` on a dict",
    ["name"],
)
server_data_write = Counter(
    "server_data_write",
    "Calls to write operations such as `__setitem__` or `update` on a dict",
    ["name"],
)
server_data_delete = Counter(
    "server_data_delete",
    "Calls to delete operations such as `__delitem__`, `pop`, or `popitem` on a dict",
    ["name"],
)

K = TypeVar("K")
V = TypeVar("V")

class _MonitorMixin():
    def _record_size(self) -> None:
        server_data_len.labels(self.name).set(len(self))
        server_data_sizeof.labels(self.name).set(sys.getsizeof(self))


class MonitoredDict(dict[K, V], _MonitorMixin):
    """A dict that reports metrics about itself to Prometheus"""

    def __init__(self, name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.name = name

    def clear(self) -> None:
        super().clear()
        self._record_size()

    def pop(self, *args) -> V:
        server_data_delete.labels(self.name).inc()
        ret = super().pop(*args)
        self._record_size()
        return ret

    def popitem(self, /) -> tuple[K, V]:
        server_data_delete.labels(self.name).inc()
        ret = super().popitem()
        self._record_size()
        return ret

    def get(self, key: K, default=None, /):
        server_data_read.labels(self.name).inc()
        return super().get(key, default)

    def update(self, *args, **kwargs) -> None:
        server_data_write.labels(self.name).inc()
        super().update(*args, **kwargs)
        self._record_size()

    def __getitem__(self, k: K) -> V:
        server_data_read.labels(self.name).inc()
        return super().__getitem__(k)

    def __setitem__(self, k: K, v: V, /) -> None:
        server_data_write.labels(self.name).inc()
        super().__setitem__(k, v)
        self._record_size()

    def __delitem__(self, k: K, /) -> None:
        server_data_delete.labels(self.name).inc()
        super().__delitem__(k)
        self._record_size()


class MonitoredDefaultDict(MonitoredDict, defaultdict[K, V]):
    pass


class MonitoredSet(set[V], _MonitorMixin):
    """A set that reports metrics about itself to Prometheus"""

    def __init__(self, name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.name = name

    def add(self, *args) -> None:
        server_data_write.labels(self.name).inc()
        super().add(*args)
        self._record_size()

    def clear(self) -> None:
        super().clear()
        self._record_size()

    def difference_update(self, *args) -> None:
        server_data_delete.labels(self.name).inc()
        super().difference_update(*args)
        self._record_size()

    def discard(self, element: V) -> None:
        server_data_delete.labels(self.name).inc()
        super().discard(element)
        self._record_size()

    def intersection_update(self, *args) -> None:
        server_data_delete.labels(self.name).inc()
        super().intersection_update(*args)
        self._record_size()

    def pop(self, *args) -> V:
        server_data_delete.labels(self.name).inc()
        ret = super().pop(*args)
        self._record_size()
        return ret

    def remove(self, *args) -> None:
        server_data_delete.labels(self.name).inc()
        super().remove(*args)
        self._record_size()

    def symmetric_difference_update(self, *args) -> None:
        # Might cause deletes as well, but doesn't make sense to report that
        server_data_write.labels(self.name).inc()
        super().symmetric_difference_update(*args)
        self._record_size()

    def update(self, *args) -> None:
        server_data_write.labels(self.name).inc()
        super().update(*args)
        self._record_size()
