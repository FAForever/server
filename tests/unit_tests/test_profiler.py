import asyncio
from unittest import mock

import pytest
from asynctest import CoroutineMock

from server.config import config
from server.profiler import Profiler
from tests.utils import fast_forward

pytestmark = pytest.mark.asyncio


@fast_forward(10)
async def test_profiler_scheduling():
    mock_player_service = []
    profiler = Profiler(
        mock_player_service, interval=0.1, duration=0.1, max_count=10, outfile=None
    )

    profiler._start()
    profiler.profiler.enable = mock.Mock()
    await asyncio.sleep(2)

    assert profiler.profile_count == 10
    assert profiler.profiler.enable.call_count == 10


@fast_forward(20)
async def test_profiler_cancel():
    mock_player_service = []
    profiler = Profiler(mock_player_service, interval=0.1, max_count=1000, outfile=None)
    profiler._run = CoroutineMock()

    profiler._start()
    await asyncio.sleep(1)
    profiler.cancel()
    await asyncio.sleep(10)

    assert profiler.profile_count < 20
    assert profiler._run.await_count < 20


@fast_forward(20)
async def test_profiler_immediately_cancelled():
    mock_player_service = []
    profiler = Profiler(mock_player_service, interval=1, max_count=10, outfile=None)
    profiler._run = CoroutineMock()

    profiler._start()
    await asyncio.sleep(0)
    profiler.cancel()
    await asyncio.sleep(10)

    assert profiler.profile_count == 0
    profiler._run.assert_not_awaited()


@fast_forward(10)
async def test_profiler():
    mock_player_service = []
    profiler = Profiler(
        mock_player_service,
        interval=0.1,
        duration=0.1,
        max_count=10,
        outfile="mock.file",
    )

    profiler._start()
    profiler.profiler.dump_stats = mock.Mock()
    await asyncio.sleep(2)

    profiler.profiler.dump_stats.assert_called()

    profiler.cancel()
    assert profiler.profiler is None


@fast_forward(10)
async def test_profiler_not_running_under_high_load():
    mock_player_service = mock.MagicMock()
    mock_player_service.__len__.return_value = 2000
    profiler = Profiler(
        mock_player_service,
        interval=0.1,
        duration=0.1,
        max_count=30,
        outfile="mock.file",
    )

    profiler._start()
    profiler.profiler.dump_stats = mock.Mock()
    await asyncio.sleep(2)

    profiler.profiler.dump_stats.assert_not_called()

    profiler.cancel()
    assert profiler.profiler is None


@fast_forward(10)
async def test_profiler_deleted_when_done():
    mock_player_service = []
    profiler = Profiler(
        mock_player_service, interval=0.1, duration=0.1, max_count=10, outfile=None
    )

    profiler._start()
    await asyncio.sleep(5)

    assert profiler.profiler is None


@fast_forward(20)
async def test_profiler_refreshing():
    config.PROFILING_COUNT = 10
    config.PROFILING_DURATION = 0.1
    config.PROFILING_INTERVAL = 0.1
    mock_player_service = []
    profiler = Profiler(mock_player_service, outfile=None)

    profiler.refresh()
    await asyncio.sleep(5)

    profiler.refresh()
    await asyncio.sleep(5)


@fast_forward(30)
async def test_profiler_refresh_cancels():
    config.PROFILING_COUNT = 100
    config.PROFILING_DURATION = 0.5
    config.PROFILING_INTERVAL = 0.5
    mock_player_service = []
    profiler = Profiler(mock_player_service, outfile=None)

    enable_mock = mock.Mock()

    profiler.refresh()
    profiler.profiler.enable = enable_mock
    await asyncio.sleep(10)

    config.PROFILING_INTERVAL = -1
    profiler.refresh()
    await asyncio.sleep(10)

    assert profiler._running is False
    assert profiler.profile_count == 0
    assert profiler.profiler is None
    assert enable_mock.call_count < 12
