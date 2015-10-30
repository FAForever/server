import asyncio
from copy import deepcopy

import config
from .decorators import with_logger


@with_logger
class NatServerProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None
        self._futures = {}

    def add_future(self, msg, fut):
        self._logger.debug("Added listener for {}".format(msg))
        self._futures[msg] = fut

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self._logger.debug("{}/udp<<: {}".format(addr, data))
        try:
            if data in self._futures:
                # Strip the \x08 byte for NAT messages
                self._futures[data].set_result((data[1:].decode(), addr))
                del self._futures[data]
        except Exception as e:
            self._logger.exception(e)

    def connection_lost(self, exc):
        # Normally losing a connection isn't something we care about
        # but for UDP transports it means trouble
        self._logger.exception(exc)

    def error_received(self, exc):
        self._logger.exception(exc)

@with_logger
class NatPacketServer:
    def __init__(self, addr=('0.0.0.0', config.LOBBY_UDP_PORT), loop=None):
        self.addr = addr
        self.loop = loop or asyncio.get_event_loop()
        self.server, self.protocol = None, None
        self._waiters = {}

    async def __aenter__(self):
        await self.listen()
        return self

    async def listen(self):
        self.server, self.protocol = await self.loop.create_datagram_endpoint(NatServerProtocol, self.addr)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.server.close()

    def await_packet(self, message: str):
        print("Awaiting message: {}".format(message))
        fut = asyncio.Future()
        self.protocol.add_future("\x08{}".format(message).encode(), fut)
        return fut

    def sendto(self, msg, addr):
        self.protocol.transport.sendto(msg, addr)
