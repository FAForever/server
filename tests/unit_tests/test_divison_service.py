# coding=utf-8
from unittest.mock import MagicMock, Mock
import pytest
from server.stats.division_service import *
from tests import CoroMock


class MockDivisionAccessor(DivisionAccessor):
    def __init__(self):
        self.update_player = CoroMock()
        self.add_player = CoroMock()
        self._divisions = [Division(1, "League 1 - Division A", 1, 10.0),
                           Division(2, "League 1 - Division B", 1, 30.0),
                           Division(3, "League 1 - Division C", 1, 50.0),
                           Division(4, "League 2 - Division D", 2, 20.0),
                           Division(5, "League 2 - Division E", 2, 60.0),
                           Division(6, "League 2 - Division F", 2, 100.0),
                           Division(7, "League 3 - Division D", 3, 100.0),
                           Division(8, "League 3 - Division E", 3, 200.0),
                           Division(9, "League 3 - Division F", 3, 9999.0)]

        self._players = [PlayerDivisionInfo(1, 1, 9.5),
                         PlayerDivisionInfo(2, 1, 49.5),
                         PlayerDivisionInfo(3, 2, 0.0),
                         PlayerDivisionInfo(4, 3, 10.0)]

    async def get_player_infos(self, season: int) -> List['PlayerDivisionInfo']:
        return self._players

    async def get_divisions(self) -> List['Division']:
        return self._divisions

    async def update_player(self, player: 'PlayerDivisionInfo') -> None:
        pass

    async def add_player(self, player: 'PlayerDivisionInfo') -> None:
        pass


@pytest.fixture()
def sample_players() -> List[PlayerDivisionInfo]:
    return [PlayerDivisionInfo(1, 1, 9.5),
            PlayerDivisionInfo(2, 1, 49.5),
            PlayerDivisionInfo(3, 2, 0.0),
            PlayerDivisionInfo(4, 3, 10.0)]


@pytest.fixture()
def division_service() -> DivisionService:
    accessor = Mock()
    accessor.get_divisions = CoroMock()

    return DivisionService(MockDivisionAccessor(), 1)

async def async_assert_player_division(division_service: DivisionService, player_id: int, division_id: int):
    assert (await division_service.get_player_division(player_id)).id == division_id


@pytest.mark.asyncio
async def test_match_in_same_division(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    await async_assert_player_division(division_service, 1, 1)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.5
    await async_assert_player_division(division_service, 2, 3)

    await division_service.post_result(1, 2, 1)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[2])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 10.5
    await async_assert_player_division(division_service, 1, 2)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.0
    await async_assert_player_division(division_service, 2, 3)


@pytest.mark.asyncio
async def test_match_in_same_division_inverted(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    await async_assert_player_division(division_service, 1, 1)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.5
    await async_assert_player_division(division_service, 2, 3)

    await division_service.post_result(2, 1, 2)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[2])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 10.5
    await async_assert_player_division(division_service, 1, 2)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.0
    await async_assert_player_division(division_service, 2, 3)


@pytest.mark.asyncio
async def test_match_winner_ascends_league(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    await async_assert_player_division(division_service, 1, 1)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.5
    await async_assert_player_division(division_service, 2, 3)

    await division_service.post_result(2, 1, 1)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[2])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.0
    await async_assert_player_division(division_service, 1, 1)
    assert division_service._players[2].league == 2
    assert division_service._players[2].score == 0.0
    await async_assert_player_division(division_service, 2, 4)


@pytest.mark.asyncio
async def test_do_not_fall_below_0(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    assert division_service._players[3].league == 2
    assert division_service._players[3].score == 0.0

    await division_service.post_result(1, 3, 1)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[3])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 11.0
    assert division_service._players[3].league == 2
    assert division_service._players[3].score == 0.0


@pytest.mark.asyncio
async def test_gain_loss_winner_inferior(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    division_service._players[3].score = 11.0

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    assert division_service._players[3].league == 2
    assert division_service._players[3].score == 11.0

    await division_service.post_result(1, 3, 1)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[3])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 11.0
    assert division_service._players[3].league == 2
    assert division_service._players[3].score == 10.0


@pytest.mark.asyncio
async def test_gain_loss_winner_superior(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    division_service._players[3].score = 11.0

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    assert division_service._players[3].league == 2
    assert division_service._players[3].score == 11.0

    await division_service.post_result(1, 3, 2)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[3])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.0
    assert division_service._players[3].league == 2
    assert division_service._players[3].score == 11.5


@pytest.mark.asyncio
async def test_new_player(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    assert 98 not in division_service._players
    assert 99 not in division_service._players

    await division_service.post_result(98, 99, 2)

    assert division_service.accessor.add_player.call_count == 2
    assert division_service.accessor.update_player.call_count == 2

    assert division_service._players[98].league == 1
    assert division_service._players[98].score == 0.0
    assert division_service._players[99].league == 1
    assert division_service._players[99].score == 1.0


@pytest.mark.asyncio
async def test_draw(division_service):
    await division_service._get_players()  # required inits for asserts before real life usage

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    await async_assert_player_division(division_service, 1, 1)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.5
    await async_assert_player_division(division_service, 2, 3)

    await division_service.post_result(1, 2, 0)

    division_service.accessor.add_player.assert_not_called()
    division_service.accessor.update_player.assert_any_call(division_service._players[1])
    division_service.accessor.update_player.assert_any_call(division_service._players[2])

    assert division_service._players[1].league == 1
    assert division_service._players[1].score == 9.5
    await async_assert_player_division(division_service, 1, 1)
    assert division_service._players[2].league == 1
    assert division_service._players[2].score == 49.5
    await async_assert_player_division(division_service, 2, 3)
