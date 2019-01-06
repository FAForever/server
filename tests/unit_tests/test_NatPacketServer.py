import asyncio
import socket
import logging

from unittest import mock

import server.config as config
from server.natpacketserver import NatPacketServer


class ClientTestProto(asyncio.DatagramProtocol):
    def __init__(self, message):
        self.message = message

    def connection_made(self, transport):
        transport.sendto(self.message)

async def test_receives_udp(loop: asyncio.BaseEventLoop):
    addr = ('127.0.0.1', config.LOBBY_UDP_PORTS[-1])
    msg = 'test'

    async with NatPacketServer(addr) as server:
        recv_fut = server.await_packet(msg)
        await loop.create_datagram_endpoint(lambda: ClientTestProto(("\x08"+msg).encode()),
                                            remote_addr=addr)
        received_msg, _ = await recv_fut
        assert received_msg == msg

async def test_sends_udp(loop: asyncio.BaseEventLoop):
    rx_addr = ('127.0.0.1', config.LOBBY_UDP_PORTS[-1])
    tx_addr = ('127.0.0.1', config.LOBBY_UDP_PORTS[-1]+1)
    msg = 'test'

    async with NatPacketServer(rx_addr) as server:
        recv_fut = server.await_packet(msg)

        async with NatPacketServer(tx_addr) as sender:
            sender.send_natpacket_to(msg, rx_addr)

        await recv_fut
        received_msg, _ = recv_fut.result()
        assert received_msg == msg

async def test_success_cleans_up(loop: asyncio.BaseEventLoop):
    rx_addr = ('127.0.0.1', config.LOBBY_UDP_PORTS[-1])
    tx_addr = ('127.0.0.1', config.LOBBY_UDP_PORTS[-1]+1)
    msg = 'Hello 1'
    async with NatPacketServer(rx_addr) as server:
        recv_fut = server.await_packet(msg)

        async with NatPacketServer(tx_addr) as sender:
            sender.send_natpacket_to(msg, rx_addr)

            await recv_fut

            assert not server.is_waiting_for(msg)

async def test_failure_cleans_up(loop: asyncio.BaseEventLoop):
    rx_addr = ('127.0.0.1', config.LOBBY_UDP_PORTS[-1])
    msg = 'Hello 1'
    async with NatPacketServer(rx_addr) as server:
        recv_fut = server.await_packet(msg)
        recv_fut.cancel()
        # Give the callback a chance to run
        await asyncio.sleep(0)
        assert not server.is_waiting_for(msg)
