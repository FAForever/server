import asyncio
import logging
from collections import Counter, defaultdict
from typing import ClassVar, Iterable, Optional

from server.decorators import with_logger
from server.matchmaker import MatchmakerQueue, MatchmakerQueueMapPool
from server.players import Player
from server.protocol import DisconnectedError
from server.types import MatchmakerQueueMapPoolVetoData

BracketID = int
MapPoolMapVersionId = int
VetoTokensApplied = int
VetosMap = dict[MapPoolMapVersionId, VetoTokensApplied]


class PlayerVetoes:
    def __init__(self):
        self._vetoes: dict[BracketID, VetosMap] = {}

    def apply_vetoes(
        self,
        new_vetoes: Optional[dict[BracketID, VetosMap]],
    ) -> Optional[list[dict]]:
        """Validates and sets vetoes based on new vetoes and pool constraints."""
        if new_vetoes is None or not self._is_valid_vetoes(new_vetoes):
            new_vetoes = self._vetoes

        pools_vetodata = VetoSystem.pools_veto_data
        adjusted_vetoes = {}
        veto_datas = []
        for bracket_id, map_ids, total_tokens, max_per_map, _ in pools_vetodata:
            bracket_vetoes = self.get_correct_vetoes_for_bracket(
                new_vetoes.get(bracket_id, {}),
                map_ids,
                total_tokens,
                max_per_map,
            )
            adjusted_vetoes[bracket_id] = bracket_vetoes
            if bracket_vetoes:
                veto_datas.extend(self.build_veto_data(bracket_id, bracket_vetoes))

        if adjusted_vetoes != self._vetoes:
            self._vetoes = adjusted_vetoes
            return veto_datas

        return None

    def _is_valid_vetoes(self, vetoes: dict) -> bool:
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

    def get_correct_vetoes_for_bracket(
        self,
        new_bracket_vetoes: VetosMap,
        map_ids: list[MapPoolMapVersionId],
        total_tokens: int,
        max_per_map: int,
    ) -> VetosMap:
        adjusted_vetoes = {}
        tokens_sum = 0
        for map_id in map_ids:
            tokens = new_bracket_vetoes.get(map_id, 0)
            tokens_applied = self.cap_tokens(tokens, tokens_sum, total_tokens, max_per_map)
            if tokens_applied > 0:
                adjusted_vetoes[map_id] = tokens_applied
                tokens_sum += tokens_applied
        return adjusted_vetoes

    def cap_tokens(
        self,
        tokens: int,
        tokens_sum: int,
        total_tokens: int,
        max_per_map: int,
    ) -> int:
        tokens_applied = max(tokens, 0)
        if tokens_sum + tokens_applied > total_tokens:
            tokens_applied = total_tokens - tokens_sum
        if max_per_map > 0 and tokens_applied > max_per_map:
            tokens_applied = max_per_map
        return tokens_applied

    def build_veto_data(self, bracket_id: BracketID, vetoes: VetosMap) -> list[dict]:
        """Builds veto data for sending to the client."""

        return [
            {
                "map_pool_map_version_id": map_id,
                "veto_tokens_applied": tokens,
                "matchmaker_queue_map_pool_id": bracket_id
            }
            for map_id, tokens in vetoes.items()
        ]

    def get_vetoes_for_bracket(self, bracket_id: BracketID) -> VetosMap:
        return self._vetoes.get(bracket_id, {})


@with_logger
class VetoSystem:
    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)
    _max_stream_count = 25
    pools_veto_data: ClassVar[list[MatchmakerQueueMapPoolVetoData]] = []

    @staticmethod
    async def apply_vetoes_to_player(
        player: Player,
        new_vetoes: Optional[dict[BracketID, VetosMap]] = None,
    ) -> None:
        """Applies vetoes for a player and sends a message if changes occur."""
        veto_datas = player.vetoes.apply_vetoes(new_vetoes)
        if veto_datas:
            try:
                await player.send_message({
                    "command": "vetoes_changed",
                    "vetoesData": veto_datas
                })
            except DisconnectedError:
                VetoSystem._logger.warning(f"Failed to send vetoes update to player {player.id}: Player disconnected")
            except Exception as e:
                VetoSystem._logger.error(f"Unexpected error sending vetoes update to player {player.id}: {str(e)}")

    @staticmethod
    async def update_vetoes_of_players(players: Iterable[Player]) -> None:
        player_queue: asyncio.Queue[Player] = asyncio.Queue()
        for player in players:
            await player_queue.put(player)

        async def worker():
            while not player_queue.empty():
                player = await player_queue.get()
                try:
                    await VetoSystem.apply_vetoes_to_player(player)
                finally:
                    player_queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(VetoSystem._max_stream_count)]
        await asyncio.gather(*workers)

    @staticmethod
    def generate_initial_weights_for_match(
        players_in_match,
        matchmaker_queue_map_pool: MatchmakerQueueMapPool,
    ) -> dict[int, int]:
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
                vetoes_map[m.map_pool_map_version_id] += player.vetoes.get_vetoes_for_bracket(pool_id).get(m.map_pool_map_version_id, 0)

        VetoSystem._logger.debug("______vetoes_map________________: %s", vetoes_map)

        if max_tokens_per_map == 0:
            max_tokens_per_map = VetoSystem.calculate_dynamic_tokens_per_map(minimum_maps_after_veto, vetoes_map.values())
            # this should never happen actually so i am not sure do we need this here or not
            if max_tokens_per_map == 0:
                VetoSystem._logger.error("calculate_dynamic_tokens_per_map received impossible vetoes setup, all vetoes cancelled for a match")
                vetoes_map = {}
                max_tokens_per_map = 1

        return {
            m.map_pool_map_version_id: max(
                0,
                1 - vetoes_map.get(m.map_pool_map_version_id, 0) / max_tokens_per_map,
            )
            for m in pool.maps.values()
        }

    @staticmethod
    def set_pools_veto_data(queues: dict[str, MatchmakerQueue]) -> bool:
        """
        # Returns
        Whether or not the veto data changed.
        """
        pools_vetodata = VetoSystem.extract_pools_veto_data(queues)

        if VetoSystem.pools_veto_data != pools_vetodata:
            VetoSystem.pools_veto_data = pools_vetodata
            return True

        return False

    @staticmethod
    def extract_pools_veto_data(queues: dict[str, MatchmakerQueue]) -> list[MatchmakerQueueMapPoolVetoData]:
        result = []
        for queue in queues.values():
            for matchmaker_queue_map_pool_id, pool, *_, veto_tokens_per_player, max_tokens_per_map, minimum_maps_after_veto in queue.map_pools.values():
                if (
                    max_tokens_per_map == 0 and minimum_maps_after_veto >= len(pool.maps)
                    or max_tokens_per_map != 0 and queue.team_size * 2 * veto_tokens_per_player / max_tokens_per_map > len(pool.maps) - minimum_maps_after_veto
                ):
                    veto_tokens_per_player = 0
                    max_tokens_per_map = 1
                    minimum_maps_after_veto = 1
                    VetoSystem._logger.error(
                        "Wrong vetoes setup detected for pool %s in queue %s",
                        pool.id,
                        queue.id,
                    )
                result.append(
                    MatchmakerQueueMapPoolVetoData(
                        matchmaker_queue_map_pool_id=matchmaker_queue_map_pool_id,
                        map_pool_map_version_ids=[map.map_pool_map_version_id for map in pool.maps.values()] + [-1],
                        veto_tokens_per_player=veto_tokens_per_player,
                        max_tokens_per_map=max_tokens_per_map,
                        minimum_maps_after_veto=minimum_maps_after_veto
                    )
                )
        return result

    @staticmethod
    def calculate_dynamic_tokens_per_map(M: float, tokens_applied_to_maps: Iterable[int]) -> float:
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
