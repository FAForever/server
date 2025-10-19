import logging
from collections import Counter, defaultdict
from typing import Any, ClassVar, Iterable, Optional

from server.core import Service
from server.decorators import with_logger
from server.exceptions import ClientError
from server.matchmaker import MatchmakerQueue, MatchmakerQueueMapPool
from server.player_service import PlayerService
from server.players import Player
from server.types import MatchmakerQueueMapPoolVetoData

BracketID = int
MapPoolMapVersionId = int
VetoTokensApplied = int
VetosMap = dict[MapPoolMapVersionId, VetoTokensApplied]


class PlayerVetoes:
    def __init__(self):
        self._vetoes: dict[BracketID, VetosMap] = {}

    def get_vetoes_for_bracket(self, bracket_id: BracketID) -> VetosMap:
        return self._vetoes.get(bracket_id, {})

    def to_dict(self) -> dict:
        return {
            "vetoes": [
                {
                    "map_pool_map_version_id": map_id,
                    "veto_tokens_applied": tokens,
                    "matchmaker_queue_map_pool_id": bracket_id
                }
                for bracket_id, vetoes in self._vetoes.items()
                for map_id, tokens in vetoes.items()
            ]
        }


@with_logger
class VetoService(Service):
    _logger: ClassVar[logging.Logger]

    def __init__(self, player_service: PlayerService):
        self.player_service = player_service

        self.pools_veto_data: list[MatchmakerQueueMapPoolVetoData] = []

    def update_pools_veto_config(self, queues: dict[str, MatchmakerQueue]) -> list[Player]:
        """
        Update the cached veto config to match the new queues.

        Returns list of players whose vetoes were force-adjusted due to config changes.
        These players should be removed from matchmaking queues.
        """

        pools_vetodata = self.extract_pools_veto_config(queues)

        if self.pools_veto_data != pools_vetodata:
            self.pools_veto_data = pools_vetodata

            pool_maps_by_bracket = {
                pool_data.matchmaker_queue_map_pool_id: set(pool_data.map_pool_map_version_ids)
                for pool_data in self.pools_veto_data
            }

            affected_players = []
            for player in self.player_service.all_players:
                # TODO: Can we avoid force adjusting veto selections for players.
                adjusted_vetoes = self._adjust_vetoes(player.vetoes._vetoes)

                if adjusted_vetoes != player.vetoes._vetoes:
                    tokens_amount_for_some_map_was_reduced = any(
                        map_id in pool_maps_by_bracket.get(bracket, set())
                        and original_tokens > adjusted_vetoes.get(bracket, {}).get(map_id, 0)
                        for bracket, bracket_vetoes in player.vetoes._vetoes.items()
                        for map_id, original_tokens in bracket_vetoes.items()
                    )
                    player.vetoes._vetoes = adjusted_vetoes
                    player.write_message({
                        "command": "vetoes_info",
                        "forced": tokens_amount_for_some_map_was_reduced,
                        **player.vetoes.to_dict(),
                    })
                    if tokens_amount_for_some_map_was_reduced:
                        affected_players.append(player)

            return affected_players

        return []

    def extract_pools_veto_config(
        self,
        queues: dict[str, MatchmakerQueue],
    ) -> list[MatchmakerQueueMapPoolVetoData]:
        result = []
        for queue in queues.values():
            for matchmaker_queue_map_pool in queue.map_pools.values():
                veto_tokens_per_player = matchmaker_queue_map_pool.veto_tokens_per_player
                max_tokens_per_map = matchmaker_queue_map_pool.max_tokens_per_map
                minimum_maps_after_veto = matchmaker_queue_map_pool.minimum_maps_after_veto

                if not _is_valid_veto_config_for_queue(queue, matchmaker_queue_map_pool):
                    veto_tokens_per_player = 0
                    max_tokens_per_map = 1
                    minimum_maps_after_veto = 1
                    self._logger.error(
                        "Wrong vetoes setup detected for pool %s in queue %s",
                        matchmaker_queue_map_pool.map_pool.id,
                        queue.id,
                    )

                result.append(
                    MatchmakerQueueMapPoolVetoData(
                        matchmaker_queue_map_pool_id=matchmaker_queue_map_pool.id,
                        map_pool_map_version_ids=[
                            map.map_pool_map_version_id
                            for map in matchmaker_queue_map_pool.map_pool.maps.values()
                        ] + [-1],
                        veto_tokens_per_player=veto_tokens_per_player,
                        max_tokens_per_map=max_tokens_per_map,
                        minimum_maps_after_veto=minimum_maps_after_veto
                    )
                )

        return result

    async def set_player_vetoes(
        self,
        player: Player,
        new_vetoes: dict[BracketID, VetosMap],
    ):
        """Validates and sets vetoes based on new vetoes and pool constraints."""
        if not _is_valid_vetoes(new_vetoes):
            raise ClientError("invalid veto data")

        adjusted_vetoes = self._adjust_vetoes(new_vetoes)

        if adjusted_vetoes != player.vetoes._vetoes:
            player.vetoes._vetoes = adjusted_vetoes
        if adjusted_vetoes != new_vetoes:
            await player.send_message({
                "command": "vetoes_info",
                "forced": False,
                **player.vetoes.to_dict(),
            })

    def _adjust_vetoes(
        self,
        new_vetoes: dict[BracketID, VetosMap],
    ) -> dict[BracketID, VetosMap]:
        # TODO: How can we avoid doing this adjustment? It would be better to
        # simply check if the veto selection is valid, and return an error if
        # not so that the client can display that to the user and force a new
        # selection. Or, if we expect the client to do that already, we can
        # simply raise a ClientError on invalid veto selections.
        adjusted_vetoes = {}
        for bracket_id, map_ids, total_tokens, max_per_map, _ in self.pools_veto_data:
            bracket_vetoes = _adjust_vetoes_for_bracket(
                new_vetoes.get(bracket_id, {}),
                map_ids,
                total_tokens,
                max_per_map,
            )
            if bracket_vetoes:
                adjusted_vetoes[bracket_id] = bracket_vetoes

        return adjusted_vetoes

    def generate_initial_weights_for_match(
        self,
        players_in_match,
        matchmaker_queue_map_pool: MatchmakerQueueMapPool,
    ) -> dict[int, float]:
        (
            pool_id,
            pool,
            *_,
            max_tokens_per_map,
            minimum_maps_after_veto
        ) = matchmaker_queue_map_pool

        vetoes_map: dict[int, int] = defaultdict(int)

        for m in pool.maps.values():
            for player in players_in_match:
                bracket_vetoes = player.vetoes.get_vetoes_for_bracket(pool_id)
                vetoes_map[m.map_pool_map_version_id] += bracket_vetoes.get(m.map_pool_map_version_id, 0)

        self._logger.debug("______vetoes_map________________: %s", vetoes_map)

        if max_tokens_per_map == 0:
            max_tokens_per_map = self.calculate_dynamic_tokens_per_map(minimum_maps_after_veto, vetoes_map.values())
            # This should never happen
            if max_tokens_per_map == 0:
                self._logger.error(
                    "calculate_dynamic_tokens_per_map received impossible "
                    "vetoes setup, all vetoes cancelled for a match",
                )
                vetoes_map = {}
                max_tokens_per_map = 1

        return {
            m.map_pool_map_version_id: max(
                0,
                1 - vetoes_map.get(m.map_pool_map_version_id, 0) / max_tokens_per_map,
            )
            for m in pool.maps.values()
        }

    def calculate_dynamic_tokens_per_map(
        self,
        M: float,
        tokens_applied_to_maps: Iterable[int],
    ) -> float:
        """
        Calculate the smallest positive T such that the sum of weights w = max((T - V)/T, 0) for each map is at least M,
        where V is the number of tokens applied to that map. If the condition is met with maps that have zero tokens, returns 1.

        The function groups maps by the number of tokens applied to them and processes these groups in ascending order of token values.
        For each group, it checks if a solution T exists such that the sum of weights for the maps considered so far is at least M.
        If a solution is found, it returns that T. If no solution is found after considering all maps, it returns 0.
        """
        def calculate_solution(
            tokens_sum: float,
            map_count: int,
            M: float,
            upper_bound: Optional[float],
        ) -> Optional[float]:
            if tokens_sum == 0 and map_count >= M:
                return 1
            if map_count > M:
                candidate = tokens_sum / (map_count - M)
                if upper_bound is None or candidate <= upper_bound:
                    return candidate
            return None

        # grouping maps with the same tokens applied count
        group_sizes = Counter(tokens_applied_to_maps)
        sorted_tokens = sorted(group_sizes.keys())

        total_map_count_in_selected_groups = 0
        total_tokens_applied_to_selected_groups = 0.0

        for i, token in enumerate(sorted_tokens):
            next_map_group_size = group_sizes[token]
            total_map_count_in_selected_groups += next_map_group_size
            total_tokens_applied_to_selected_groups += token * next_map_group_size
            upper_bound = sorted_tokens[i + 1] if i < len(sorted_tokens) - 1 else None
            solution = calculate_solution(total_tokens_applied_to_selected_groups, total_map_count_in_selected_groups, M, upper_bound)
            if solution is not None:
                return solution

        return 0


def _is_valid_veto_config_for_queue(
    queue: MatchmakerQueue,
    queue_config: MatchmakerQueueMapPool,
) -> bool:
    num_maps = len(queue_config.map_pool.maps)

    if (
        queue_config.max_tokens_per_map == 0
        and queue_config.minimum_maps_after_veto >= num_maps
    ):
        return False

    if queue_config.max_tokens_per_map != 0:
        total_players = queue.team_size * 2
        vetoable_maps_per_player = queue_config.veto_tokens_per_player / queue_config.max_tokens_per_map
        vetoable_maps = total_players * vetoable_maps_per_player

        # tokens/map > number of maps that may be vetoed
        # TODO: because vetoable_maps >= 0 this inequality also implies
        # queue_config.minimum_maps_after_veto > num_maps
        # Why is it strictly greater than here but greater than or equal to above?
        if vetoable_maps > num_maps - queue_config.minimum_maps_after_veto:
            return False

    return True


def _is_valid_vetoes(vetoes: Any) -> bool:
    return (
        isinstance(vetoes, dict)
        and all(
            isinstance(k, int)
            and isinstance(v, dict)
            and all(
                isinstance(mk, int) and isinstance(mv, int) and mv >= 0
                for mk, mv in v.items()
            )
            for k, v in vetoes.items()
        )
    )


def _adjust_vetoes_for_bracket(
    new_bracket_vetoes: VetosMap,
    map_ids: list[MapPoolMapVersionId],
    total_tokens: int,
    max_per_map: float,
) -> VetosMap:
    assert total_tokens >= 0

    adjusted_vetoes = {}
    tokens_sum = 0
    for map_id in map_ids:
        tokens = new_bracket_vetoes.get(map_id, 0)
        tokens_applied = _cap_tokens(
            tokens,
            total_tokens - tokens_sum,
            max_per_map,
        )

        if tokens_applied > 0:
            adjusted_vetoes[map_id] = tokens_applied
            tokens_sum += tokens_applied

    return adjusted_vetoes


def _cap_tokens(
    tokens: int,
    total_remaining: int,
    max_per_map: float,
) -> int:
    assert total_remaining >= 0

    applied = min(max(tokens, 0), total_remaining)

    if max_per_map > 0:
        applied = min(applied, max_per_map)

    return applied
