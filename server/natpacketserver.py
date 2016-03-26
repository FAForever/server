import asyncio
from typing import Dict

import server
from .decorators import with_logger

@with_logger
class NatServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, address, futures):
        self.transport = None
        self._address = address
        self._futures = futures

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            self._logger.debug("{}: {}/udp<<: {}".format(self._address, addr, data))
            msg = data[1:].decode()
            if data in self._futures:
                # Strip the \x08 byte for NAT messages
                if not self._futures[data].done():
                    self._futures[data].set_result((msg, addr))
        except UnicodeDecodeError:
            # We don't care about random folks sending us data
            pass
        except Exception as e:
            self._logger.exception(e)

    def sendto(self, msg, addr):
        self.transport.sendto(msg, addr)

    def connection_lost(self, exc):
        # Normally losing a connection isn't something we care about
        # but for UDP transports it means trouble
        self._logger.exception("NatServerProtocol({}) exc: {}".format(self._address, exc))

    def error_received(self, exc):
        self._logger.exception("NatServerProtocol({}) exc: {}".format(self._address, exc))


@with_logger
class NatPacketServer:
    instance = None

    def __init__(self, addresses=None, loop=None):
        if not addresses:
            self.addresses = ('0.0.0.0', 6112)
        else:
            self.addresses = addresses if type(addresses) is list else [addresses]
        self.ports = [int(address[1]) for address in self.addresses]
        self.loop = loop or asyncio.get_event_loop()
        self.servers = {}
        self._futures = {}  # type: Dict[bytes, asyncio.Future]
        NatPacketServer.instance = self

    async def __aenter__(self):
        await self.listen()
        return self

    async def listen(self):
        for address in self.addresses:
            try:
                server, protocol = await self.loop.create_datagram_endpoint(lambda: NatServerProtocol(address, self._futures), address)
                self.servers[server] = protocol
            except OSError:
                self._logger.warn('Could not open UDP socket {}:{}'.format(address[0], address[1]))

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for server in self.servers:
            server.close()

    @staticmethod
    def prefixed(msg: str) -> bytes:
        """
        The game uses \x08 as a prefix for NAT packets
        :param msg:
        :return:
        """
        return "\x08{}".format(msg).encode()

    def is_waiting_for(self, msg: str) -> bool:
        return self.prefixed(msg) in self._futures

    def _add_future(self, msg: str, fut) -> None:
        self._logger.debug("Added listener for {}".format(msg))
        server.stats.gauge("NatPacketProtocol.futures", len(self._futures))
        self._futures[self.prefixed(msg)] = fut
        fut.add_done_callback(lambda f: self._remove_future(msg))

    def await_packet(self, message: str) -> asyncio.Future:
        future = asyncio.Future()
        self._add_future(message, future)
        return future

    def send_natpacket_to(self, msg: str, addr):
        for server, protocol in self.servers.items():
            self._logger.debug(">>{}/udp: {}".format(addr, msg))
            protocol.transport.sendto(self.prefixed(msg), addr)
            return

    def _remove_future(self, msg: str):
        del self._futures[self.prefixed(msg)]
