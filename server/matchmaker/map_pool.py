import logging
import random
from collections import Counter
from typing import ClassVar, Iterable, NamedTuple, Optional

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

    def choose_map(self, played_map_ids: Iterable[int] = (), vetoes_map=None, max_tokens_per_map=1) -> Map:
        """
        Select a random map using veto system weights with an anti-repetition adjustment.
        """
        if not self.maps:
            self._logger.critical("Trying to choose a map from an empty map pool: %s", self.name)
            raise RuntimeError(f"Map pool {self.name} not set!")

        if vetoesMap is None:
            vetoesMap = {}

        PRIMARY_THRESHOLD = 0.75
        SECONDARY_THRESHOLD = 0.5

        # Filter and count played map IDs
        repetition_counts = Counter(id_ for id_ in played_map_ids if id_ in self.maps)
        self._logger.debug(f"Repetition counts: {repetition_counts}")
        sorted_maps = [id_ for id_, _ in repetition_counts.most_common()]
        self._logger.debug(f"Sorted maps: {sorted_maps}")
        # Initial weights based on vetoes
        initial_weights = {id_: max(0, 1 - vetoes_map.get(id_, 0) / max_tokens_per_map) for id_ in self.maps}
        self._logger.debug(f"Vetoes: {vetoes_map}")
        self._logger.debug(f"Initial weights: {initial_weights}")
        adjusted_weights = initial_weights.copy()

        # Anti-repetition adjustment
        for id_ in sorted_maps:
            current_weight = initial_weights[id_]
            candidates = []
            for threshold in [PRIMARY_THRESHOLD, SECONDARY_THRESHOLD]:
                candidates = [
                    other_id for other_id in self.maps if other_id != id_
                    and repetition_counts[other_id] < repetition_counts[id_]
                    and initial_weights[other_id] >= threshold * current_weight
                    and adjusted_weights[other_id] > 0
                ]
                if candidates:
                    break
            if candidates:
                v = adjusted_weights[id_]
                sum_candidates = sum(initial_weights[other_id] for other_id in candidates)
                for other_id in candidates:
                    adjusted_weights[other_id] += (initial_weights[other_id] / sum_candidates) * v
                adjusted_weights[id_] = 0
        self._logger.debug(f"Adjusted weights: {adjusted_weights}")
        map_list = list(self.maps.items())
        final_weights = [adjusted_weights[id_] * map.weight for id_, map in map_list]
        self._logger.debug(f"Final weights: {final_weights}")
        return random.choices([map for _, map in map_list], weights=final_weights, k=1)[0].get_map()

    def __repr__(self) -> str:
        return f"MapPool({self.id}, {self.name}, {list(self.maps.values())})"


class MatchmakerQueueMapPool(NamedTuple):
    id: int
    map_pool: MapPool
    min_rating: Optional[int]
    max_rating: Optional[int]
    veto_tokens_per_player: int
    max_tokens_per_map: int
    minimum_maps_after_veto: float
