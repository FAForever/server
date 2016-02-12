import socket
from asyncio.protocols import DatagramProtocol
from unittest import mock
from unittest.mock import Mock, patch

import asyncio
import pytest

from server import NatPacketServer
from server.connectivity import ConnectivityTest, Connectivity
from server.players import Player
from tests.utils import CoroMock


@pytest.fixture()
def player():
    return mock.create_autospec(Player(login='Dummy', id=42))


@pytest.fixture()
def connectivity():
    return mock.create_autospec(Connectivity)

async def test_test_public(loop, player, connectivity):
    natserver = mock.create_autospec(NatPacketServer(addresses=[
        ('0.0.0.0', 6112)
    ]))
    natserver.ports = [6112]

    fut = asyncio.Future()
    fut.set_result(('127.0.0.1', 6112))
    connectivity.wait_for_natpacket = lambda _: fut

    connectivity_test = ConnectivityTest(connectivity, '127.0.0.1', 6112, player)
    connectivity_test._natserver = natserver

    await connectivity_test.test_public()

    assert natserver.send_natpacket_to.called


async def test_test_stun(loop, player, connectivity):
    natserver = mock.create_autospec(NatPacketServer(addresses=[
        ('0.0.0.0', 6112), ('0.0.0.0', 30351)
    ]))
    natserver.ports = [6112, 30351]

    future = asyncio.Future()
    natserver.await_packet.return_value = future

    def send(command_id, args):
        addr, msg = args
        host, port = addr.split(':')
        if int(port) in natserver.ports:
            if not future.done():
                future.set_result((msg, (host, int(port))))
    connectivity.send = send
    connectivity.drain = CoroMock()

    connectivity_test = ConnectivityTest(connectivity, '', 0, player)
    connectivity_test._natserver = natserver

    await connectivity_test.test_stun()

    msg, (host, port) = future.result()
    assert port in natserver.ports
