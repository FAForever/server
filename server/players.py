from contextlib import suppress
from enum import Enum, unique
from typing import Optional, Union

from server.config import config
from server.rating import PlayerRatings, RatingType, RatingTypeMap

from .factions import Faction
from .protocol import DisconnectedError
from .weakattr import WeakAttribute


@unique
class PlayerState(Enum):
    IDLE = 1
    PLAYING = 2
    HOSTING = 3
    JOINING = 4
    SEARCHING_LADDER = 5


class Player:
    """
    Standard player object used for representing signed-in players.

    In the context of a game, the Game object holds game-specific
    information about players.
    """

    lobby_connection = WeakAttribute["LobbyConnection"]()
    game = WeakAttribute["Game"]()
    game_connection = WeakAttribute["GameConnection"]()

    def __init__(
        self,
        login: str = None,
        session: int = 0,
        player_id: int = 0,
        ratings=None,
        clan=None,
        game_count=None,
        lobby_connection: Optional["LobbyConnection"] = None
    ) -> None:
        self._faction = Faction.uef

        self.id = player_id
        self.login = login

        # The player_id of the user in the `login` table of the database.
        self.session = session

        self.ratings = PlayerRatings(
            lambda: (config.START_RATING_MEAN, config.START_RATING_DEV)
        )
        if ratings is not None:
            self.ratings.update(ratings)

        self.game_count = RatingTypeMap(int)
        if game_count is not None:
            self.game_count.update(game_count)

        # social
        self.avatar = None
        self.clan = clan
        self.country = None

        self.friends = set()
        self.foes = set()

        self.user_groups = set()

        self.state = PlayerState.IDLE

        if lobby_connection is not None:
            self.lobby_connection = lobby_connection

    @property
    def faction(self) -> Faction:
        return self._faction

    @faction.setter
    def faction(self, value: Union[str, int, Faction]) -> None:
        if isinstance(value, str):
            self._faction = Faction.from_string(value)
        elif isinstance(value, int):
            self._faction = Faction(value)
        elif isinstance(value, Faction):
            self._faction = value
        else:
            raise TypeError(f"Unsupported faction type {type(value)}!")

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

        :raises: DisconnectedError if the player has disconnected.
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

    def to_dict(self):
        """
        Return a dictionary representing this player object
        :return:
        """

        def filter_none(t):
            _, v = t
            return v is not None

        return dict(
            filter(
                filter_none, (
                    ("id", self.id),
                    ("login", self.login),
                    ("avatar", self.avatar),
                    ("country", self.country),
                    ("clan", self.clan),
                    ("ratings", {
                        rating_type: {
                            "rating": self.ratings[rating_type],
                            "number_of_games": self.game_count[rating_type]
                        }
                        for rating_type in self.ratings
                    }),
                    # Deprecated
                    ("global_rating", self.ratings[RatingType.GLOBAL]),
                    ("ladder_rating", self.ratings[RatingType.LADDER_1V1]),
                    ("number_of_games", self.game_count[RatingType.GLOBAL]),
                )
            )
        )

    def __str__(self) -> str:
        return (f"Player({self.login}, {self.id}, "
                f"{self.ratings[RatingType.GLOBAL]}, "
                f"{self.ratings[RatingType.LADDER_1V1]})")

    def __repr__(self) -> str:
        return self.__str__()

    def __hash__(self) -> int:
        return self.id

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.id == other.id
