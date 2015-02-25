import asyncio
from unittest import mock
from src.connectivity import TestPeer, Connectivity
from src.gameconnection import GameConnection


def test_TestPeer_tests_public(loop):
    identifier = 2
    game_connection = mock.Mock()
    @asyncio.coroutine
    def test():
        with TestPeer(game_connection, '127.0.0.1', 6112, identifier) as peer_test:
            connectivity = asyncio.async(peer_test.determine_connectivity())
            peer_test.handle_ProcessNatPacket(['Are you public? {}'.format(identifier)])
            yield from connectivity
            assert connectivity.result() == Connectivity.PUBLIC
    loop.run_until_complete(test())

def test_TestPeer_tests_stun(loop):
    identifier = 2
    game_connection = mock.Mock()
    @asyncio.coroutine
    def test():
        with TestPeer(game_connection, '127.0.0.1', 6112, identifier) as peer_test:
            connectivity = asyncio.async(peer_test.determine_connectivity())
            peer_test.handle_ProcessServerNatPacket(['Hello {}'.format(identifier)])
            yield from connectivity
            assert connectivity.result() == Connectivity.STUN
    loop.run_until_complete(test())

def test_TestPeer_tests_proxy(loop):
    identifier = 2
    game_connection = mock.Mock()
    @asyncio.coroutine
    def test():
        with TestPeer(game_connection, '127.0.0.1', 6112, identifier) as peer_test:
            connectivity = yield from peer_test.determine_connectivity()
            assert connectivity == Connectivity.PROXY
    loop.run_until_complete(test())


