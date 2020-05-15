from enum import Enum
from typing import Dict, MutableMapping, Tuple, TypeVar, Union

from trueskill import Rating


# Values correspond to legacy table names. This will be fixed when db gets
# migrated.
class RatingType(Enum):
    GLOBAL = "global"
    LADDER_1V1 = "ladder_1v1"


K = Union[RatingType, str, int]
V = TypeVar("V")


class RatingTypeMap(MutableMapping[K, V]):
    """
    A mapping who's keys are RatingType's or leaderboard id's.

    # Example
    Suppose global.id = 1

    mapping = RatingTypeMap(default=0)
    mapping[1] = 10
    assert mapping[RatingType.GLOBAL] == 10
    assert mapping[RatingType.LADDER_1V1] == 0
    """

    _rating_id_map: Dict[str, int] = {}
    _fake_id = -1

    def __init__(self, default: V, rating_id_map: Dict[str, int] = {}):
        super().__init__()
        self._rating_id_map: Dict[str, int] = rating_id_map
        self._back: Dict[int, V] = {}
        # In case we don't have a rating_id_map we will use some fake keys.
        # We use negative numbers as these will not conflict with database ids.
        self._default = default

    @classmethod
    def clear(cls):
        cls._rating_id_map.clear()

    @classmethod
    def _get_fake_id(cls, key: Union[RatingType, str]) -> int:
        if isinstance(key, RatingType):
            str_key = key.value
        else:
            str_key = key

        int_key = cls._fake_id
        cls._fake_id -= 1
        cls._rating_id_map[str_key] = int_key

        return int_key

    def __back_key(self, key: K) -> int:
        """
        Get the appropriate key for the _back map.
        """
        if isinstance(key, int):
            return key
        elif isinstance(key, str):
            return RatingTypeMap._rating_id_map[key]
        elif isinstance(key, RatingType):
            try:
                return RatingTypeMap._rating_id_map[key.value]
            except KeyError:
                return self._get_fake_id(key)

        raise KeyError(key)

    def __getitem__(self, key: K) -> V:
        int_id = self.__back_key(key)

        try:
            return self._back[int_id]
        except KeyError:
            if int_id in RatingTypeMap._rating_id_map.values():
                self._back[int_id] = self._default
                return self._default
            else:
                raise

    def __setitem__(self, key: K, value: V) -> None:
        self._back[self.__back_key(key)] = value

    def __delitem__(self, key: K) -> None:
        del self._back[self.__back_key(key)]

    def __iter__(self):
        return iter(self._back)

    def __len__(self) -> int:
        return len(self._back)


# Only used to coerce rating type.
class PlayerRatings(RatingTypeMap[Tuple[float, float]]):
    def __setitem__(self, key: K, value: Tuple[float, float]):
        if isinstance(value, Rating):
            val = (value.mu, value.sigma)
        else:
            val = value
        super().__setitem__(key, val)
