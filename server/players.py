import weakref
from enum import Enum, unique

from server.rating import RatingType, RatingTypeMap, PlayerRatings
from .factions import Faction


@unique
class PlayerState(Enum):
    IDLE = 1,
    PLAYING = 2,
    HOSTING = 3,
    JOINING = 4,
    SEARCHING_LADDER = 5,


class Player:
    """
    Standard player object used for representing signed-in players.

    In the context of a game, the Game object holds game-specific
    information about players.
    """

    def __init__(
        self,
        login: str = None,
        session: int = 0,
        player_id: int = 0,
        ratings=None,
        clan=None,
        game_count=None,
        permission_group: int = 0,
        lobby_connection: "LobbyConnection" = None
    ):
        self._faction = 0

        self.id = player_id
        self.login = login

        # The player_id of the user in the `login` table of the database.
        self.session = session

        self.ratings = PlayerRatings(default=(1500, 500))
        if ratings is not None:
            self.ratings.update(ratings)

        self.game_count = RatingTypeMap(0)
        if game_count is not None:
            self.game_count.update(game_count)

        # social
        self.avatar = None
        self.clan = clan
        self.country = None

        self.friends = set()
        self.foes = set()

        self.admin = permission_group >= 2
        self.mod = permission_group >= 1

        self.state = PlayerState.IDLE

        self.faction = 1

        self._lobby_connection = lambda: None
        if lobby_connection is not None:
            self.lobby_connection = lobby_connection

        self._game = lambda: None
        self._game_connection = lambda: None

    @property
    def faction(self):
        return self._faction

    @faction.setter
    def faction(self, value):
        if isinstance(value, str):
            self._faction = Faction.from_string(value)
        else:
            self._faction = value

    @property
    def lobby_connection(self) -> "LobbyConnection":
        """
        Weak reference to the LobbyConnection of this player
        """
        return self._lobby_connection()

    @lobby_connection.setter
    def lobby_connection(self, value: "LobbyConnection"):
        self._lobby_connection = weakref.ref(value)

    @property
    def game(self):
        """
        Weak reference to the Game object that this player wants to join or is
        currently in
        """
        return self._game()

    @game.setter
    def game(self, value):
        self._game = weakref.ref(value)

    @game.deleter
    def game(self):
        self._game = lambda: None

    @property
    def game_connection(self):
        """
        Weak reference to the GameConnection object for this player
        :return:
        """
        return self._game_connection()

    @game_connection.setter
    def game_connection(self, value):
        self._game_connection = weakref.ref(value)

    @game_connection.deleter
    def game_connection(self):
        self._game_connection = lambda: None

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
                    ('id', self.id),
                    ('login', self.login),
                    ('global_rating', self.ratings[RatingType.GLOBAL]),
                    ('ladder_rating', self.ratings[RatingType.LADDER_1V1]),
                    ('number_of_games', self.game_count[RatingType.GLOBAL]),
                    ('avatar', self.avatar),
                    ('country', self.country),
                    ('clan', self.clan),
                )
            )
        )

    def __str__(self):
        return (f"Player({self.login}, {self.id}, "
                f"{self.ratings[RatingType.GLOBAL]}, "
                f"{self.ratings[RatingType.LADDER_1V1]})")

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        if not isinstance(other, Player):
            return False
        else:
            return self.id == other.id
