from unittest import mock

import asyncio
import pytest

from server.connectivity import TestPeer, Connectivity, ConnectivityState

slow = pytest.mark.slow

async def test_connectivity_defaults_to_proxy(loop):
    identifier = '2'
    game_connection = mock.Mock()
    async def nope(x):
        await asyncio.sleep(55)

    game_connection.wait_for_natpacket = nope
    with TestPeer(game_connection, '127.0.0.1', 6112, identifier) as peer_test:
        connectivity = await peer_test.determine_connectivity()
        assert connectivity == Connectivity(addr=None,
                                            state=ConnectivityState.PROXY)

