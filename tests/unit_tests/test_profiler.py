from server.config import config
from server.profiler import Profiler, get_profiler_factory

import asyncio
import pytest
from unittest import mock
from asynctest import CoroutineMock

from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


@fast_forward(10)
async def test_profiler_scheduling():
    mock_player_service = []
    interval = 0.1
    profiler = Profiler(
        interval, mock_player_service, duration=0.1, max_count=10, outfile=None
    )
    profiler.profiler.enable = mock.Mock()

    profiler.start()
    await asyncio.sleep(2)

    assert profiler.profile_count == 10
    assert profiler.profiler.enable.call_count == 10


@fast_forward(20)
async def test_profiler_cancel():
    mock_player_service = []
    interval = 0.1
    profiler = Profiler(interval, mock_player_service, max_count=1000, outfile=None)
    profiler._run = CoroutineMock()

    profiler.start()
    await asyncio.sleep(1)
    profiler.cancel()
    await asyncio.sleep(10)

    assert profiler.profile_count < 20
    assert profiler._run.await_count < 20


@fast_forward(20)
async def test_profiler_immediately_cancelled():
    mock_player_service = []
    interval = 1
    profiler = Profiler(interval, mock_player_service, max_count=10, outfile=None)
    profiler._run = CoroutineMock()

    profiler.start()
    await asyncio.sleep(0)
    profiler.cancel()
    await asyncio.sleep(10)

    assert profiler.profile_count == 0
    profiler._run.assert_not_awaited()


@fast_forward(10)
async def test_profiler():
    mock_player_service = []
    interval = 0.1
    profiler = Profiler(
        interval, mock_player_service, duration=0.1, max_count=10, outfile="mock.file"
    )
    profiler.profiler.dump_stats = mock.Mock()

    profiler.start()
    await asyncio.sleep(2)

    profiler.profiler.dump_stats.assert_called()

    profiler.cancel()
    assert profiler.profiler is None


@fast_forward(10)
async def test_profiler_not_running_under_high_load():
    mock_player_service = mock.MagicMock()
    mock_player_service.__len__.return_value = 2000
    interval = 0.1
    profiler = Profiler(
        interval, mock_player_service, duration=0.1, max_count=30, outfile="mock.file"
    )
    profiler.profiler.dump_stats = mock.Mock()

    profiler.start()
    await asyncio.sleep(2)

    profiler.profiler.dump_stats.assert_not_called()

    profiler.cancel()
    assert profiler.profiler is None


@fast_forward(10)
async def test_profiler_deleted_when_done():
    mock_player_service = []
    interval = 0.1
    profiler = Profiler(
        interval, mock_player_service, duration=0.1, max_count=10, outfile=None
    )

    profiler.start()
    await asyncio.sleep(5)

    assert profiler.profiler is None


async def test_profiler_factory():
    mock_player_service = []
    make_profiler = get_profiler_factory(mock_player_service, start=False)

    config["PROFILING_INTERVAL"] = 10
    config["PROFILING_DURATION"] = 2
    config["PROFILING_COUNT"] = 300

    profiler = make_profiler()

    assert profiler._player_service is mock_player_service


async def test_profiler_factory_negative_interval():
    mock_player_service = []
    make_profiler = get_profiler_factory(mock_player_service)

    config["PROFILING_INTERVAL"] = -1

    profiler = make_profiler()

    assert profiler is None
