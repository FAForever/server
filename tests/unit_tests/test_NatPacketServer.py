import asyncio
import socket
import logging

from unittest import mock

import config
from server.natpacketserver import NatPacketServer


class TestClientProto(asyncio.DatagramProtocol):
    def __init__(self, message):
        self.message = message

    def connection_made(self, transport):
        transport.sendto(self.message)

async def test_receives_udp(loop: asyncio.BaseEventLoop):
    addr = ('127.0.0.1', config.LOBBY_UDP_PORT)
    msg = 'test'

    async with NatPacketServer(addr) as server:
        recv_fut = server.await_packet(msg)
        await loop.create_datagram_endpoint(lambda: TestClientProto(("\x08"+msg).encode()),
                                            remote_addr=addr)
        await recv_fut
        received_msg, _ = recv_fut.result()
        assert received_msg == msg

async def test_sends_udp(loop: asyncio.BaseEventLoop):
    rx_addr = ('127.0.0.1', config.LOBBY_UDP_PORT)
    tx_addr = ('127.0.0.1', config.LOBBY_UDP_PORT+1)
    msg = 'test'

    async with NatPacketServer(rx_addr) as server:
        recv_fut = server.await_packet(msg)

        async with NatPacketServer(tx_addr) as sender:
            sender.sendto(("\x08"+msg).encode(), rx_addr)

        await recv_fut
        received_msg, _ = recv_fut.result()
        assert received_msg == msg
