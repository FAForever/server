import random
from collections import Counter
from typing import Iterable

from ..decorators import with_logger
from ..types import Map


@with_logger
class MapPool(object):
    def __init__(
        self,
        map_pool_id: int,
        name: str,
        maps: Iterable[Map] = ()
    ):
        self.id = map_pool_id
        self.name = name
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
        least_count = least_common[0][1]
        # Trim off the maps with higher play counts
        for i, (_, count) in enumerate(least_common):
            if count != least_count:
                least_common = least_common[:i]
                break

        return self.maps[random.choice(least_common)[0]]
