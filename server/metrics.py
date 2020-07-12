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
    ["user_agent"],
)

user_logins = Counter(
    "server_user_logins_total", "Total number of login attempts made", ["status"]
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
