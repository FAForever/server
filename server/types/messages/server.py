"""Messages originating from the server"""

from typing import Any, Literal, Optional, TypedDict, Union

from typing_extensions import NotRequired

ServerMessage = Union[
    "AuthenticationFailed",
    "Avatar",
    "CoopInfo",
    "Disabled",
    "GameInfo",
    "GameInfoList",
    "GameJoinFailed",
    "GameLaunch",
    "IceServers",
    "Invalid",
    "IRCPassword",
    "KickedFromParty",
    "MatchCancelled",
    "MatchFound",
    "MatchmakerInfo",
    "ModvaultInfo",
    "Notice",
    "PartyInvite",
    "Ping",
    "PlayerInfo",
    "Pong",
    "SearchInfo",
    "SearchTimeout",
    "SearchViolation",
    "Session",
    "Social",
    "UpdateParty",
    "Welcome",
]


class AuthenticationFailed(TypedDict):
    """Authentication request failed.

    **Example**
    ```json
    {
        "command": "authentication_failed",
        "text": "Cannot find user id"
    }
    ```
    """

    command: Literal["authentication_failed"]

    text: str
    """Reason message to display to the user."""


class Avatar(TypedDict):
    """Information about available avatars.

    **Example**
    ```json
    {
        "command": "avatar",
        "avatarlist": [
            {
                "url": "http://content.faforever.com/avatars/example.png",
                "tooltip": "Example"
            }
        ]
    }
    ```
    """

    command: Literal["avatar"]

    avatarlist: list["AvatarAvatarlist"]
    """Reason message to display to the user."""


class AvatarAvatarlist(TypedDict):
    """Type for `Avatar.avatarlist`."""

    url: str
    """HTTP url for the avatar image."""

    tooltip: str
    """Avatar tooltip."""


class CoopInfo(TypedDict):
    """Information about a coop mission.

    **Example**
    ```json
    {
        "command": "coop_info",
        "uid": 1234,
        "type": "FA Campaign",
        "name": "Operation Black Day",
        "description": "Description for Operation Black Day",
        "filename": "maps/scmp_coop_123.v0002.zip",
        "featured_mod": "coop"
    }
    ```
    """

    command: Literal["coop_info"]

    uid: int
    """Database id."""

    type: str
    """Which campaign the mission belongs to."""

    name: str
    """Mission name."""

    description: str
    """Mission description."""

    filename: str
    """Mission file name."""

    featured_mod: Literal["coop"]


class Disabled(TypedDict):
    """The requested functionality has been disabled.

    This can happen when the server is in standby mode during a graceful
    shutdown. Certain actions such as hosting and joining games will be disabled.

    **Example**
    ```json
    {
        "command": "disabled",
        "request": "game_host"
    }
    ```
    """

    command: Literal["disabled"]

    request: str
    """The `command` value of the message that was disabled."""


class GameInfo(TypedDict):
    """Information about a game.

    **Example**
    ```json
    {
        "command": "game_info",
        "visibility": "public",
        "password_protected": false,
        "uid": 1234,
        "title": "200+",
        "state": "open",
        "game_type": "custom",
        "featured_mod": "faf",
        "sim_mods": {
            "foo-mod-id": "Mod display name"
        },
        "mapname": "scmp_001",
        "map_file_path": "maps/scmp_001.zip",
        "host": "username",
        "host_id": 1234,
        "num_players": 4,
        "max_players": 4,
        "hosted_at": "2020-01-01T01:02:03.123456+00:00",
        "launched_at": 1234567.891234,
        "rating_type": "global",
        "rating_min": 200.0,
        "rating_max": null,
        "enforce_rating_range": false,
        "teams_ids": [
            {
                "team_id": 1,
                "player_ids": [1, 2, 3]
            }
        ],
        "teams": {
            "1": ["username", "username2", "username3"]
        }
    }
    ```
    """

    command: Literal["game_info"]

    visibility: Literal["friends", "public"]
    """Game visibility."""

    password_protected: bool
    """Whether or not a password is required to join the game."""

    uid: int
    """Game id."""

    title: str
    """Game title."""

    state: Literal["closed", "open", "playing"]
    """Game state."""

    game_type: Literal["coop", "custom", "matchmaker"]
    """Game type."""

    featured_mod: str
    """Featured mod name."""

    sim_mods: dict[str, str]
    """Mapping of mod uid to display name for each sim mod used."""

    mapname: str
    """Map name."""

    map_file_path: str
    """Map name formatted like `maps/{name}.zip`.

    DEPRECATED: Use `mapname` instead
    """

    host: str
    """Username of the host player."""

    num_players: int
    """Number of players connected to the game."""

    max_players: int
    """Total slots for players."""

    hosted_at: Optional[str]
    """The ISO formatted datetime at which the game was hosted or `None` if
    the game is still waiting for the host to connect.
    """

    launched_at: Optional[float]
    """Unix timestamp when the game was launched or `None` if the game is
    still in lobby.
    """

    rating_type: str
    """The leaderboard technical name that will be used to rate the game and
    enforce the rating range.
    """

    rating_min: Optional[float]
    """Minimum displayed rating desired by the host, if any.

    Displayed rating is `mean - (3 * dev)`.
    """

    rating_max: Optional[float]
    """Maximum displayed rating desired by the host, if any.

    Displayed rating is `mean - (3 * dev)`.
    """

    enforce_rating_range: bool
    """Whether or not min/max_rating will be enforced when players try to join
    the game.
    """

    teams_ids: list["GameInfoTeam"]
    """Team setup information."""

    teams: dict[int, list[str]]
    """Team setup information.

    DEPRECATED: Use `teams_ids` instead.
    """


class GameInfoList(TypedDict):
    """Information about multiple games

    **Example**
    ```json
    {
        "command": "game_info",
        "games": [
            {
                "command": "game_info",
                "visibility": "public",
                "password_protected": false,
                "uid": 1234,
                "title": "200+",
                "state": "open",
                "game_type": "custom",
                "featured_mod": "faf",
                "sim_mods": {
                    "foo-mod-id": "Mod display name"
                },
                "mapname": "scmp_001",
                "map_file_path": "maps/scmp_001.zip",
                "host": "username",
                "host_id": 1234,
                "num_players": 4,
                "max_players": 4,
                "hosted_at": "2020-01-01T01:02:03.123456+00:00",
                "launched_at": 1234567.891234,
                "rating_type": "global",
                "rating_min": 200.0,
                "rating_max": null,
                "enforce_rating_range": false,
                "teams_ids": [
                    {
                        "team_id": 1,
                        "player_ids": [1, 2, 3]
                    }
                ],
                "teams": {
                    "1": ["username", "username2", "username3"]
                }
            }
        ]
    }
    ```
    """

    command: Literal["game_info"]

    games: list[GameInfo]


class GameInfoTeam(TypedDict):
    """Type for `GameInfo.teams_ids`."""

    team_id: int
    """Team id."""

    player_ids: list[int]
    """List of team member player ids."""


class GameJoinFailed(TypedDict):
    """The attempt to join the game failed.

    **Example**
    ```json
    {
        "command": "game_join_failed",
        "reason": "bad_password",
        "uid": 1234
    }
    ```
    """

    command: Literal["game_join_failed"]

    reason: Literal["bad_password", "game_not_ready", "host_left_game"]
    """Reason code."""

    uid: int
    """The game id that the player failed to join."""


class GameLaunch(TypedDict):
    """Tells the client to launch a new ForgedAlliance process.

    **Example**
    ```json
    {
        "command": "game_launch",
        "args": ["/numgames", 123],
        "uid": 1234,
        "mod": "faf",
        "name": "Rhiza vs Dostya",
        "init_mode": 1,
        "game_type": "matchmaker",
        "rating_type": "ladder1v1",
        "mapname": "scmp_001",
        "team": 1,
        "faction": 1,
        "expected_players": 2,
        "map_position": 1,
        "game_options": {
            "Share": "ShareUntilDeath",
            "UnitCap": 500
        }
    }
    ```
    """

    command: Literal["game_launch"]

    args: list[Union[str, int]]
    """Command line arguments to be passed to ForgedAlliance.exe."""

    uid: int
    """The game id."""

    mod: str
    """The featured mod to use."""

    name: str
    """The game title."""

    init_mode: int
    """

    DEPRICATED: init_mode can be inferred from game_type"""

    game_type: Literal["coop", "custom", "matchmaker"]
    """Game type."""

    rating_type: str
    """The leaderboard technical name that will be used to rate the game."""

    mapname: NotRequired[str]
    """Name of the map to use."""

    team: NotRequired[int]
    """The team to play on.

    Used in AUTO_LOBBY matches to set the team.
    """

    faction: NotRequired[int]
    """The faction to use.

    Used in AUTO_LOBBY matches to set the faction.
    """

    expected_players: NotRequired[int]
    """Expected number of players.

    Used in AUTO_LOBBY matches to wait for the game to be ready.
    """

    map_position: NotRequired[int]
    """The start spot to use.

    Used in AUTO_LOBBY matches to set the start spot.
    """

    game_options: NotRequired[dict[str, Any]]
    """Additional game options to set.

    Used in AUTO_LOBBY matches.
    """


class IceServers(TypedDict):
    """
    DEPRECATED: ICE servers are handled by the icebreaker service.

    **Example**
    ```json
    {
        "command": "ice_servers",
        "ice_servers": []
    }
    ```
    """

    command: Literal["ice_servers"]

    ice_servers: list[Any]
    """Always empty."""


class Invalid(TypedDict):
    """The command sent by the client was invalid.

    **Example**
    ```json
    {
        "command": "invalid"
    }
    ```
    """

    command: Literal["invalid"]


class IRCPassword(TypedDict):
    """The password to use when logging into the IRC server.

    DEPRECATED: The lobby server no longer handles IRC passwords.

    **Example**
    ```json
    {
        "command": "irc_password",
        "password": "deprecated"
    }
    ```
    """

    command: Literal["irc_password"]

    password: str
    """The password."""


class KickedFromParty(TypedDict):
    """Sent when the player is kicked from their current party by the owner via
    `server.types.messages.client.KickPlayerFromParty`.

    **Example**
    ```json
    {
        "command": "kicked_from_party"
    }
    ```
    """

    command: Literal["kicked_from_party"]


class MatchCancelled(TypedDict):
    """Send when a matchmaker match was unable to start.

    This can be sent either directly after `MatchFound`, in which case the host
    failed to setup the lobby and there will be no follow up `GameLaunch`
    message, or after `GameLaunch`, in which case the game failed to start and
    should be aborted.

    Once `MatchCancelled` has been received, it is important that the client
    terminate the running ForgedAlliance.exe process associated with the
    cancelled game id. If the game is allowed to stay open, it is possible for
    the connection to succeed after the server timeout, and players to end up
    playing a matchmaker game that will not be rated and will not be recorded
    in the database.

    **Example**
    ```json
    {
        "command": "match_cancelled",
        "game_id": 1234
    }
    ```
    """

    command: Literal["match_cancelled"]

    game_id: Optional[int]
    """The id of the game that failed to start."""


class MatchFound(TypedDict):
    """Send when a matchmaker match has been found.

    This signals the successful end of a matchmaker search attempt, and the
    start of an automatch setup. Automatch setup will either end with a
    `GameLaunch` message that succesfully starts a game, or a `MatchCancelled`
    message signaling that game setup failed. If `MatchCancelled` is received
    directly after `MatchFound`, then the host failed to setup the lobby. In
    this case there will be no `GameLaunch` message. If `GameLaunch` is recieved
    and then `MatchCancelled` is received with the corresponding game id, then
    the game failed to start and should be aborted.

    **Example**
    ```json
    {
        "command": "match_found",
        "queue_name": "ladder1v1"
    }
    ```
    """

    command: Literal["match_found"]

    queue_name: str
    """The queue for which a match was found."""


class MatchmakerInfo(TypedDict):
    """Information about matchmaker queues.

    **Example**
    ```json
    {
        "command": "matchmaker_info",
        "queues": [
            {
                "queue_name": "ladder1v1",
                "queue_pop_time": "2020-01-01T01:02:03.123456+00:00",
                "queue_pop_time_delta": 123.45,
                "num_players": 10,
                "boundary_80s": [(0, 400), (100, 500)],
                "boundary_75": [(100, 300), (200, 400)],
                "team_size": 2
            }
        ]
    }
    ```
    """

    command: Literal["matchmaker_info"]

    queues: list["MatchmakerInfoQueue"]
    """Updated queue info for a list of queues.

    This will be a subset of the available queues that have had a state change
    since the last update message, so if a queue is missing from the list, it
    should still be retained in the client state / UI.
    """


class MatchmakerInfoQueue(TypedDict):
    """Type for `MatchmakerInfo.queues`."""

    queue_name: str
    """The queue technical name.

    This name is used when requesting to join the queue via
    `server.types.messages.client.GameMatchmaking`.
    """

    queue_pop_time: str
    """The ISO formatted datetime at which the queue will pop."""

    queue_pop_time_delta: float
    """The number of seconds until the queue will pop.

    It is prefered to use `queue_pop_time` instead as this will avoid any
    inconsistencies with network latency, however, if clock sync is an issue on
    the local system then `queue_pop_time_delta` can be used to calculate the
    approximate pop time.
    """

    num_players: int
    """The total number of players currently in the queue."""

    boundary_80s: list[tuple[int, int]]
    """Rating boundaries that achieve roughly 80% quality."""

    boundary_75s: list[tuple[int, int]]
    """Rating boundaries that achieve roughly 75% quality."""

    team_size: int
    """The size of teams that games created by this queue will have.

    This is also the maximum party size allowed when joining the queue.
    """


class ModvaultInfo(TypedDict):
    """DEPRECATED: Use the API to manage mods."""

    command: Literal["modvault_info"]
    thumbnail: Any
    link: Any
    bugreports: list[Any]
    comments: list[Any]
    description: Any
    played: Any
    likes: Any
    downloads: Any
    date: Any
    uid: Any
    name: Any
    version: Any
    author: Any
    ui: Any


# DEPRECATED: Notice messages should not be used for new features. Instead,
# implement a feature specific message class with machine friendly error codes.
class Notice(TypedDict):
    """Display an informational message to the user.

    **Example**
    ```json
    {
        "command": "notice",
        "style": "info",
        "text": "Message from server"
    }
    ```
    """

    command: Literal["notice"]

    style: Literal["error", "info", "kick", "kill"]
    """Styling mode."""

    text: NotRequired[str]
    """The text to display."""


class PartyInvite(TypedDict):
    """Sent when someone has invited the current player to join their party.

    **Example**
    ```json
    {
        "command": "party_invite",
        "sender": 1234
    }
    ```
    """

    command: Literal["party_invite"]

    sender: int
    """The id of the player who sent the party invite."""


class Ping(TypedDict):
    """Ping message to create traffic on the network socket.

    **Example**
    ```json
    {
        "command": "ping"
    }
    ```
    """

    command: Literal["ping"]


class PlayerInfo(TypedDict):
    """Information about players.

    **Example**
    ```json
    {
        "command": "player_info"
        "players": [
            {
                "id": 1234,
                "login": "username",
                "avatar": "http://content.faforever.com/avatars/example.png",
                "country": "US",
                "clan": "ACC",
                "state": "offline",
                "ratings": {
                    "global": {
                        "rating": [1000, 100],
                        "number_of_games": 1234,
                    },
                    "ladder1v1": {
                        "rating": [800, 150],
                        "number_of_games": 1234,
                    },
                    "tmm2v2": {
                        "rating": [1100, 100],
                        "number_of_games": 1234,
                    }
                },
                "global_rating": [1000, 100],
                "ladder_rating": [800, 150],
                "number_of_games": 1234
            }
        ]
    }
    ```
    """

    command: Literal["player_info"]

    players: list["PlayerInfoPlayer"]
    """Updated queue info for a list of players.

    This will be a subset of players that have had a state change since the last
    update message, so if a player is missing from the list, they should still
    be retained in the client state / UI.

    Players should be removed from the client state / UI if the player `state`
    is `"offline"`.
    """


class PlayerInfoPlayer(TypedDict):
    """Type for `PlayerInfo.players`."""

    id: int
    """The player id."""

    login: str
    """The player's username."""

    avatar: NotRequired["PlayerInfoPlayerAvatar"]
    """The currently selected avatar."""

    country: str
    """The two character country code."""

    clan: NotRequired[str]
    """The three character clan code."""

    state: NotRequired[str]
    """The player state.

    Currently only the value 'offline' is sent when a player has disconnected.
    """

    ratings: dict[str, "PlayerInfoPlayerRating"]
    """The player's rating information."""

    global_rating: tuple[float, float]
    """The player's global rating.

    DEPRECATED: Use `ratings["global"]["rating"]` instead.
    """

    ladder_rating: tuple[float, float]
    """The player's ladder1v1 rating.

    DEPRECATED: Use `ratings["ladder1v1"]["rating"]` instead.
    """

    number_of_games: int
    """The total number of global rated games played.

    DEPRECATED: Use `ratings["global"]["number_of_games"]` instead.
    """


class PlayerInfoPlayerAvatar(TypedDict):
    """Type for `PlayerInfoPlayer.ratings`."""

    url: str
    """The avatar URL."""

    tooltip: str
    """The avatar tooltip to show in the client."""


class PlayerInfoPlayerRating(TypedDict):
    """Type for `PlayerInfoPlayer.ratings`."""

    rating: tuple[float, float]
    """The rating mean, deviation."""

    number_of_games: int
    """The total number of games played for this rating type."""


class Pong(TypedDict):
    """Sent when a `Ping` message is received.

    **Example**
    ```json
    {
        "command": "pong"
    }
    ```
    """

    command: Literal["pong"]


class SearchInfo(TypedDict):
    """Information about the state of the current player's search in some
    matchmaker queue.

    **Example**
    ```json
    {
        "command": "search_info",
        "queue_name": "ladder1v1",
        "state": "start"
    }
    ```
    """

    command: Literal["search_info"]

    queue_name: str
    """The name of the queue that the search applies to."""

    state: Literal["start", "stop"]
    """The state of the search."""


class SearchTimeout(TypedDict):
    """Sent when a player attempts to join a matchmaker queue, but one or more
    players in their party have received a temporary matchmaker ban.

    **Example**
    ```json
    {
        "command": "search_timeout",
        "timeouts": [
            {
                "player": 1234,
                "expires_at": "2020-01-01T01:02:03.123456+00:00"
            },
            {
                "player": 12345,
                "expires_at": "2020-01-01T01:02:03.123456+00:00"
            }
        ]
    }
    ```
    """

    command: Literal["search_timeout"]

    timeouts: list["SearchTimeoutTimeout"]
    """List of timeout information for timed out players in the party that
    attempted to search.
    """


class SearchTimeoutTimeout(TypedDict):
    """Type for `SearchTimeout.timeouts`."""

    player: int
    """The player id of the player who received a search timeout."""

    expires_at: str
    """The ISO formatted datetime after which the player will be able to queue
    again.
    """


class SearchViolationBody(TypedDict):
    """Type for `SearchViolation`."""

    count: int
    """The cumulative number of violations received."""

    time: str
    """The ISO formatted datetime after which the player will be able to queue
    again.
    """


class SearchViolation(SearchViolationBody):
    """Sent when a matchmaker violation is registered for the current player.

    **Example**
    ```json
    {
        "command": "search_violation",
        "count": 1234,
        "time": "2020-01-01T01:02:03.123456+00:00"
    }
    ```
    """

    command: Literal["search_violation"]


class Session(TypedDict):
    """The session id to pass to `faf-uid`.

    **Example**
    ```json
    {
        "command": "session",
        "session": 1234
    }
    ```
    """

    command: Literal["session"]

    session: int
    """Session id."""


class Social(TypedDict):
    """Information about social functions for the player.

    **Example**
    ```json
    {
        "command": "social",
        "autojoin": ["aeolus"],
        "channels": ["aeolus"],
        "friends": [1, 2, 3],
        "foes": [4, 5, 6],
        "power": 0
    }
    ```
    """

    command: Literal["social"]

    # TODO: Deprecate one of these?
    autojoin: list[str]
    """A list of IRC channels to join."""

    channels: NotRequired[list[str]]
    """A list of IRC channels to join."""

    friends: NotRequired[list[int]]
    """List of friends ids."""

    foes: NotRequired[list[int]]
    """List of foes ids."""

    power: NotRequired[int]
    """Category to group the player under.

    0 - Regular user
    1 - Moderator
    2 - Admin
    """


class UpdatePartyBody(TypedDict):
    """Type for `UpdateParty`."""

    owner: int
    """The player id of the party owner."""

    members: list["UpdatePartyMember"]
    """
    """


class UpdateParty(UpdatePartyBody):
    """Sent when a party is updated.

    **Example**
    ```json
    {
        "command": "update_party",
        "owner": 1234,
        "members": [
            {
                "player": 1234,
                "factions": ["cybran", "uef"]
            },
            {
                "player": 12345,
                "factions": ["aeon", "seraphim"]
            }
        ]
    }
    ```
    """

    command: Literal["update_party"]


class UpdatePartyMember(TypedDict):
    """Type for `UpdatePartyBody.members`."""

    player: int
    """The member's player id."""

    factions: list[str]
    """The member's selected faction."""


class Welcome(TypedDict):
    """Send after the player has succesfully authenticated.

    **Example**
    ```json
    {
        "command": "welcome"
        "me": {
            "id": 1234,
            "login": "username",
            "avatar": "http://content.faforever.com/avatars/example.png",
            "country": "US",
            "clan": "ACC",
            "state": "offline",
            "ratings": {
                "global": {
                    "rating": [1000, 100],
                    "number_of_games": 1234,
                },
                "ladder1v1": {
                    "rating": [800, 150],
                    "number_of_games": 1234,
                },
                "tmm2v2": {
                    "rating": [1100, 100],
                    "number_of_games": 1234,
                }
            },
            "global_rating": [1000, 100],
            "ladder_rating": [800, 150],
            "number_of_games": 1234
        },
        "current_time": "2020-01-01T01:02:03.123456+00:00",
        "id": 1234,
        "login": "username"
    }
    ```
    """

    command: Literal["welcome"]

    me: PlayerInfoPlayer
    """Player information about the logged in user."""

    current_time: str
    """The ISO formatted current datetime."""

    id: int
    """The player id.

    DEPRECATED: Use `me['id']` instead.
    """

    login: str
    """The player username.

    DEPRECATED: Use `me['login']` instead.
    """
