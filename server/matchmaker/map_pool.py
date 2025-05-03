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

    def apply_antirepetition_adjustment(self, initial_weights: dict[int, float], played_map_ids: Iterable[int], base_thresholds: list[float], repeat_factor: float) -> dict[int, float]:
        """
            Transfers weights from played maps to not-played (if possible) or less-played (otherwise) maps,
            base_thresholds and repeat_factor adjusts the level of respect to the veto system:
            base_thresholds used to determine, which not-played maps are available as transfer targets
            the bigger the repeat_factor, the stronger algo tries to get rid of maps with playcount >= 2
        """
        notzero_weights = {map_id: weight for map_id, weight in initial_weights.items() if weight > 0}
        repetition_counts = Counter(map_id for map_id in played_map_ids if map_id in notzero_weights)
        adjusted_weights = notzero_weights.copy()

        def get_notrepeated_weight_transfer_targets(current_weight, rep_count):
            for base_threshold in base_thresholds:
                targets = [
                    target_id for target_id in notzero_weights
                    if repetition_counts.get(target_id, 0) == 0 and
                    notzero_weights[target_id] >= base_threshold * repeat_factor ** (rep_count - 1) * current_weight
                ]
                if targets:
                    return targets
            return []

        def get_repeated_weight_transfer_targets(current_weight, rep_count):
            return [
                target_id for target_id in notzero_weights
                if 0 < (target_rep := repetition_counts.get(target_id, 0)) < rep_count and
                notzero_weights[target_id] >= repeat_factor ** (rep_count - target_rep) * current_weight
            ]

        def transfer_weight_proportionally(from_id, to_ids):
            v = adjusted_weights[from_id]
            adjusted_weights[from_id] = 0
            weight_sum = sum(notzero_weights[c] for c in to_ids)
            for c in to_ids:
                adjusted_weights[c] += (notzero_weights[c] / weight_sum) * v

        for map_id, rep_count in repetition_counts.most_common():
            current_weight = notzero_weights[map_id]
            notrepeated_targets = get_notrepeated_weight_transfer_targets(current_weight, rep_count)
            repeated_targets = get_repeated_weight_transfer_targets(current_weight, rep_count)
            weight_transfer_targets = notrepeated_targets or repeated_targets
            if weight_transfer_targets:
                transfer_weight_proportionally(map_id, weight_transfer_targets)

        return adjusted_weights

    def choose_map(self, played_map_ids: Iterable[int] = (), initial_weights: dict[int, float] = None) -> Map:
        """
            Selects a random map using veto system weights with an anti-repetition adjustment.
        """
        if not self.maps:
            self._logger.critical("Trying to choose a map from an empty map pool: %s", self.name)
            raise RuntimeError(f"Map pool {self.name} not set!")

        if initial_weights is None:
            initial_weights = {map_id: 1 for map_id in self.maps.keys()}

        adjusted_weights = self.apply_antirepetition_adjustment(
            initial_weights, played_map_ids, config.LADDER_ANTI_REPETITION_WEIGHT_BASE_THRESHOLDS, config.LADDER_ANTI_REPETITION_REPEAT_COUNTS_FACTOR
        )
        self._logger.debug("______adjusted_weights________________: %s", adjusted_weights)
        map_list = [(m.get_map().map_pool_map_version_id, m) for m in self.maps.values()]
        self._logger.debug("______map_list________________: %s", map_list)
        final_weights = [adjusted_weights.get(mp_mv_id, 0) * m.weight for mp_mv_id, m in map_list]
        self._logger.debug("______final_weights________________: %s", final_weights)
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
