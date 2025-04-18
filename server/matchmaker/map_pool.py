import logging
import random
from collections import Counter
from typing import ClassVar, Iterable, NamedTuple, Optional

from server.config import config

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

    def apply_antirepetition_adjustment(self, initial_weights: dict[int, float], played_map_ids: Iterable[int], thresholds: list[float]) -> dict[int, float]:
        notzero_weights = {map_id: weight for map_id, weight in initial_weights.items() if weight > 0}
        repetition_counts = Counter(map_id for map_id in played_map_ids if map_id in notzero_weights)
        adjusted_weights = notzero_weights.copy()

        for map_id, rep_count in repetition_counts.most_common():
            current_weight = notzero_weights[map_id]
            for threshold in thresholds:
                candidates = [
                    other_id for other_id in notzero_weights
                    if (
                        repetition_counts.get(other_id, 0) < rep_count
                        and notzero_weights[other_id] >= (
                            threshold ** (rep_count - repetition_counts.get(other_id, 0))
                            * current_weight
                        )
                    )
                ]
                if candidates:
                    v = adjusted_weights[map_id]
                    adjusted_weights[map_id] = 0
                    sum_candidates = sum(notzero_weights[c] for c in candidates)
                    for c in candidates:
                        adjusted_weights[c] += (notzero_weights[c] / sum_candidates) * v
                    break
        return adjusted_weights

    def choose_map(self, played_map_ids: Iterable[int] = (), vetoes_map=None, max_tokens_per_map=1) -> Map:
        if not self.maps:
            self._logger.critical("Trying to choose a map from an empty map pool: %s", self.name)
            raise RuntimeError(f"Map pool {self.name} not set!")

        if vetoes_map is None:
            vetoes_map = {}

        initial_weights = {id_: max(0, 1 - vetoes_map.get(id_, 0) / max_tokens_per_map) for id_ in self.maps}
        adjusted_weights = self.apply_antirepetition_adjustment(
            initial_weights, played_map_ids, config.LADDER_ANTI_REPETITION_WEIGHT_THRESHOLDS
        )

        map_list = list(self.maps.items())
        final_weights = [adjusted_weights[id_] * map.weight for id_, map in map_list]
        return random.choices([map for _, map in map_list], weights=final_weights, k=1)[0].get_map()

    def __repr__(self) -> str:
        return f"MapPool({self.id}, {self.name}, {list(self.maps.values())})"


class MatchmakerQueueMapPool(NamedTuple):
    id: int
    map_pool: MapPool
    min_rating: Optional[int]
    max_rating: Optional[int]
    veto_tokens_per_player: int
    max_tokens_per_map: float
    minimum_maps_after_veto: float
