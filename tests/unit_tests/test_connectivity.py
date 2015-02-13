import asyncio
from unittest import mock
from src.connectivity import TestPeer, Connectivity, ConnectToHost
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

def test_ConnectToHost_public_public(loop, players):
    host_conn, peer_conn = mock.Mock(spec=GameConnection), mock.Mock(spec=GameConnection)
    host, peer = players.hosting, players.joining
    host_conn.player = host
    peer_conn.player = peer
    fut = asyncio.Future()
    fut.set_result(Connectivity.PUBLIC)
    host_conn.connectivity_state = fut
    peer_conn.connectivity_state = fut
    @asyncio.coroutine
    def test():
        yield from ConnectToHost(host_conn, peer_conn)
        host_conn.send_ConnectToPeer.assert_called_with(peer.address_and_port, peer.login, peer.id )
        peer_conn.send_JoinGame.assert_called_with(host.address_and_port,
                                                   False,
                                                   host.getLogin(),
                                                   host.getId())
    loop.run_until_complete(test())

def test_ConnectToHost_public_stun(loop, players):
    host_conn, peer_conn = mock.Mock(spec=GameConnection), mock.Mock(spec=GameConnection)
    host, peer = players.hosting, players.joining
    host_conn.player = host
    peer_conn.player = peer
    public = asyncio.Future()
    stun = asyncio.Future()
    public.set_result(Connectivity.PUBLIC)
    stun.set_result(Connectivity.STUN)
    host_conn.connectivity_state = public
    peer_conn.connectivity_state = stun
    @asyncio.coroutine
    def test():
        yield from ConnectToHost(host_conn, peer_conn)
        peer_conn.send_SendNatPacket.assert_called_with(host.address_and_port, 'Connect to {}'.format(peer.id))

    loop.run_until_complete(test())

def test_ConnectToHost_stun_public(loop, players):
    host_conn, peer_conn = mock.Mock(spec=GameConnection), mock.Mock(spec=GameConnection)
    host, peer = players.hosting, players.joining
    host_conn.player = host
    peer_conn.player = peer
    public = asyncio.Future()
    stun = asyncio.Future()
    public.set_result(Connectivity.PUBLIC)
    stun.set_result(Connectivity.STUN)
    host_conn.connectivity_state = stun
    peer_conn.connectivity_state = public
    @asyncio.coroutine
    def test():
        yield from ConnectToHost(host_conn, peer_conn)
        host_conn.send_SendNatPacket.assert_called_with(host.address_and_port, 'Connect to {}'.format(peer.id))

    loop.run_until_complete(test())
