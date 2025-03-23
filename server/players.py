"""
Player type definitions
"""

from collections import defaultdict
from contextlib import suppress
from enum import Enum, unique
import logging
from typing import TYPE_CHECKING, Optional, Union, ClassVar
from .decorators import with_logger
from .types import MatchmakerQueueMapPoolVetoData
from .factions import Faction
from .protocol import DisconnectedError
from .rating import Leaderboard, PlayerRatings, RatingType
from .weakattr import WeakAttribute

if TYPE_CHECKING:
    from server.gameconnection import GameConnection
    from server.games import Game
    from server.lobbyconnection import LobbyConnection

BracketID = int
MapPoolMapVersionId = int
VetoTokensApplied = int
PlayerVetoes = dict[BracketID, dict[MapPoolMapVersionId, VetoTokensApplied]]

@unique
class PlayerState(Enum):
    IDLE = 1
    PLAYING = 2
    HOSTING = 3
    JOINING = 4
    SEARCHING_LADDER = 5
    STARTING_AUTOMATCH = 6
    STARTING_GAME = 7

@with_logger
class Player:
    _logger: ClassVar[logging.Logger]
    """
    Standard player object used for representing signed-in players.

    In the context of a game, the Game object holds game-specific
    information about players.
    """

    lobby_connection: WeakAttribute["LobbyConnection"] = WeakAttribute()
    game: WeakAttribute["Game"] = WeakAttribute()
    game_connection: WeakAttribute["GameConnection"] = WeakAttribute()

    def __init__(
        self,
        login: str,
        session: int = 0,
        player_id: int = 0,
        leaderboards: dict[str, Leaderboard] = {},
        ratings: Optional[PlayerRatings] = None,
        clan: Optional[str] = None,
        game_count: Optional[dict[str, int]] = None,
        lobby_connection: Optional["LobbyConnection"] = None
    ) -> None:
        self._faction = Faction.uef
        self._vetoes = {}

        # The player_id of the user in the `login` table of the database.
        self.id = player_id
        self.login = login

        self.session = session

        self.ratings = PlayerRatings(leaderboards)
        if ratings is not None:
            self.ratings.update_with_transient(ratings)

        self.game_count: dict[str, int] = defaultdict(int)
        if game_count is not None:
            self.game_count.update(game_count)

        # social
        self.avatar: Optional[dict[str, str]] = None
        self.clan = clan
        self.country: Optional[str] = None

        self.friends: set[int] = set()
        self.foes: set[int] = set()

        self.user_groups: set[str] = set()

        self.state = PlayerState.IDLE

        if lobby_connection is not None:
            self.lobby_connection = lobby_connection

    @property
    def faction(self) -> Faction:
        return self._faction

    @faction.setter
    def faction(self, value: Union[str, int, Faction]) -> None:
        if isinstance(value, Faction):
            self._faction = value
        else:
            self._faction = Faction.from_value(value)

    @property
    def vetoes(self) -> PlayerVetoes:
        return self._vetoes

    @vetoes.setter
    def vetoes(self, value: PlayerVetoes) -> None:
        if not isinstance(value, dict) or \
            not all(
                isinstance(k, int) and 
                isinstance(v, dict) and 
                all(isinstance(mk, int) and isinstance(mv, int) and mv >= 0 
                    for mk, mv in v.items())
                for k, v in value.items()
            ):
            raise ValueError("Invalid vetoes structure")
        self._vetoes = value

    async def update_vetoes(self, pools_vetodata: list[MatchmakerQueueMapPoolVetoData], current: dict = None) -> None:
        if current is None:
            current = self.vetoes
        fixedVetoes = {}
        vetoDatas = []
        for (matchmaker_queue_map_pool_id, map_pool_map_version_ids, veto_tokens_per_player, max_tokens_per_map, _) in pools_vetodata:
            tokens_sum = 0
            cur_bracket_vetoes = current.get(matchmaker_queue_map_pool_id, {})
            cur_fixed_vetoes = {}
            for map_id in map_pool_map_version_ids:
                new_tokens_applied = max(cur_bracket_vetoes.get(map_id, 0), 0)
                if (tokens_sum + new_tokens_applied > veto_tokens_per_player):
                    new_tokens_applied = veto_tokens_per_player - tokens_sum
                if (max_tokens_per_map > 0 and new_tokens_applied > max_tokens_per_map):
                    new_tokens_applied = max_tokens_per_map
                if (new_tokens_applied == 0):
                    continue
                vetoDatas.append({"map_pool_map_version_id": map_id, "veto_tokens_applied": new_tokens_applied, "matchmaker_queue_map_pool_id": matchmaker_queue_map_pool_id})
                cur_fixed_vetoes[map_id] = new_tokens_applied
                tokens_sum += new_tokens_applied
            if tokens_sum > 0:
                fixedVetoes[matchmaker_queue_map_pool_id] = cur_fixed_vetoes
        if fixedVetoes == self.vetoes == current:
            return
        self.vetoes = fixedVetoes
        if self.lobby_connection is None:
            return
        await self.lobby_connection.send({
            "command": "vetoes_changed",
            "vetoesData": vetoDatas
        })

    def power(self) -> int:
        """An artifact of the old permission system. The client still uses this
        number to determine if a player gets a special category in the user list
        such as "Moderator"
        """
        if self.is_admin():
            return 2
        if self.is_moderator():
            return 1

        return 0

    def is_admin(self) -> bool:
        return "faf_server_administrators" in self.user_groups

    def is_moderator(self) -> bool:
        return "faf_moderators_global" in self.user_groups

    async def send_message(self, message: dict) -> None:
        """
        Try to send a message to this player.

        # Errors
        Raises `DisconnectedError` if the player has disconnected.
        """
        if self.lobby_connection is None:
            raise DisconnectedError("Player has disconnected!")

        await self.lobby_connection.send(message)

    def write_message(self, message: dict) -> None:
        """
        Try to queue a message to be sent to this player.

        Does nothing if the player has disconnected.
        """
        if self.lobby_connection is None:
            return

        with suppress(DisconnectedError):
            self.lobby_connection.write(message)

    def to_dict(self) -> dict:
        """
        Return a dictionary representing this player object
        """
        assert self.state is not None and self.state.value is not None

        cmd = {
            "id": self.id,
            "login": self.login,
            "avatar": self.avatar,
            "country": self.country,
            "clan": self.clan,
            # NOTE: We are only sending an 'offline' state for now to signal to
            # the client when a player disconnects. However, this could be
            # expanded in the future to expose more of the internal state
            # tracking to the client to make the UI for showing players in game
            # more correct.
            "state": None if self.lobby_connection else "offline",
            "ratings": {
                rating_type: {
                    "rating": self.ratings[rating_type],
                    "number_of_games": self.game_count[rating_type]
                }
                for rating_type in self.ratings
            },
            # DEPRECATED: Use ratings instead
            "global_rating": self.ratings[RatingType.GLOBAL],
            "ladder_rating": self.ratings[RatingType.LADDER_1V1],
            "number_of_games": self.game_count[RatingType.GLOBAL],
        }
        return {k: v for k, v in cmd.items() if v is not None}

    def __str__(self) -> str:
        return (f"Player({self.login}, {self.id}, "
                f"{self.ratings[RatingType.GLOBAL]}, "
                f"{self.ratings[RatingType.LADDER_1V1]})")

    def __repr__(self) -> str:
        return (f"Player(login={self.login}, session={self.session}, "
                f"id={self.id}, ratings={dict(self.ratings)}, "
                f"clan={self.clan}, game_count={dict(self.game_count)})")
