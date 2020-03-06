from prometheus_client import Counter, Gauge, Histogram


matches = Gauge("server_matchmaker_queue_matches", "Number of matches made", ["queue"])
match_quality = Histogram(
    "server_matchmaker_queue_quality", "Quality of matches made", ["queue"]
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
)
matchmaker_players = Gauge(
    "server_matchmaker_queue_players", "Players in the queue at pop time", ["queue"]
)
matchmaker_queue_pop = Gauge(
    "server_matchmaker_queue_pop_timer_seconds",
    "Queue pop timer duration in seconds",
    ["queue"],
)

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

server_connections = Counter(
    "server_lobbyconnections_total",
    "Total number of connections to the lobby as per lobbyconnection.on_connection_made",
)
sent_messages = Counter("server_messages_total", "Total number of Messages sent")
unauth_messages = Counter(
    "server_messages_unauthenticated_total",
    "Total number of unauthenticated messages",
    ["command"],
)
server_broadcasts = Counter(
    "server_broadcasts_total", "Total number of broadcasts", ["protocol"]
)

connection_on_message_received = Histogram(
    "server_on_message_received_seconds",
    "Seconds spent in 'connection.on_message_received'",
)


active_games = Gauge(
    "server_game_active_games_total", "Number of currently active games."
    "Includes games in lobby, games currently running, and games that ended"
    "but are still in the game_service.", ["game_mode", "game_state"]
)
