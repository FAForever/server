import random
from collections import Counter
from typing import Iterable, Union

from ..decorators import with_logger
from ..types import Map, NeroxisGeneratedMap


@with_logger
class MapPool(object):
    def __init__(
        self,
        map_pool_id: int,
        name: str,
        maps: Iterable[Union[Map, NeroxisGeneratedMap]] = ()
    ):
        self.id = map_pool_id
        self.name = name
        self.maps = None
        self.set_maps(maps)

    def set_maps(self, maps: Iterable[Map]) -> None:
        self.maps = {map_.id: map_ for map_ in maps}

    def choose_map(self, played_map_ids: Iterable[int] = ()) -> Map:
        """
        Select a random map who's id does not appear in `played_map_ids`. If
        all map ids appear in the list, then pick one that appears the least
        amount of times.
        """
        if not self.maps:
            self._logger.critical(
                "Trying to choose a map from an empty map pool: %s", self.name
            )
            raise RuntimeError(f"Map pool {self.name} not set!")

        # Make sure the counter has every available map
        counter = Counter(self.maps.keys())
        counter.update(id_ for id_ in played_map_ids if id_ in self.maps)

        least_common = counter.most_common()[::-1]
        least_count = 1
        for id_, count in least_common:
            if isinstance(self.maps[id_], Map):
                least_count = count
                break

        # Trim off the maps with higher play counts
        for i, (_, count) in enumerate(least_common):
            if count > least_count:
                least_common = least_common[:i]
                break

        weights = [self.maps[id_].weight for id_, _ in least_common]

        return self.maps[random.choices(least_common, weights=weights, k=1)[0][0]].get_map()

    def __repr__(self):
        return f"MapPool({self.id}, {self.name}, {list(self.maps.values())})"
