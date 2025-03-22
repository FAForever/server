import logging
import random
from collections import Counter
from typing import ClassVar, Iterable, NamedTuple

from ..decorators import with_logger
from ..types import Map, MapPoolMap


@with_logger
class MapPool(object):
    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        map_pool_id: int,
        name: str,
        maps: Iterable[MapPoolMap] = ()
    ):
        self.id = map_pool_id
        self.name = name
        self.set_maps(maps)

    def set_maps(self, maps: Iterable[MapPoolMap]) -> None:
        self.maps = {map_.id: map_ for map_ in maps}

    def choose_map(self, played_map_ids, vetoes_map={}, max_tokens_per_map=1) -> Map:
        """
        Select a random map using veto system weights.
        The maps which are least played from played_map_ids
        and not vetoed by any player are getting x2 weight multiplier.
        """
        if not self.maps:
            self._logger.critical(
                "Trying to choose a map from an empty map pool: %s", self.name
            )
            raise RuntimeError(f"Map pool {self.name} not set!")

        # Anti-repetition is temporary disabled
        # map_list = list((map.map_pool_map_version_id, map, 2 if (map.id in least_common_ids) and (vetoes_map.get(map.map_pool_map_version_id, 0) == 0) else 1) for map in self.maps.values())
        map_list = list((map.map_pool_map_version_id, map) for map in self.maps.values())
        weights = [max(0, (1 - vetoes_map.get(id, 0) / max_tokens_per_map) * map.weight) for id, map in map_list]
        return random.choices(map_list, weights=weights, k=1)[0][1]

    def __repr__(self) -> str:
        return f"MapPool({self.id}, {self.name}, {list(self.maps.values())})"


class MatchmakerQueueMapPool(NamedTuple):
    id: int
    map_pool: MapPool
    min_rating: int | None
    max_rating: int | None
    veto_tokens_per_player: int
    max_tokens_per_map: int
    minimum_maps_after_veto: float
