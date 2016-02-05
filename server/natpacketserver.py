import asyncio
from .decorators import with_logger, _logger

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
            msg = data[1:].decode()
            if data in self._futures:
                # Strip the \x08 byte for NAT messages
                if not self._futures[data].done():
                    self._futures[data].set_result((msg, addr))
                del self._futures[data]
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
        self._logger.exception(exc)

    def error_received(self, exc):
        self._logger.exception(exc)

    def remove_future(self, msg):
        if msg in self._futures:
            fut = self._futures[msg]
            if not fut.done():
                fut.cancel()
            del self._futures[msg]


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
        self._waiters = {}
        NatPacketServer.instance = self

    async def __aenter__(self):
        await self.listen()
        return self

    async def listen(self):
        for address in self.addresses:
            try:
                server, protocol = await self.loop.create_datagram_endpoint(NatServerProtocol, address)
                self.servers[server] = protocol
            except OSError:
                _logger.warn('Could not open UDP socket {}:{}'.format(address[0], address[1]))

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for server in self.servers:
            server.close()

    def await_packet(self, message: str):
        future = asyncio.Future()
        for server, protocol in self.servers.items():
            protocol.add_future("\x08{}".format(message).encode(), future)
        return future

    def send_natpacket_to(self, msg: str, addr):
        for server, protocol in self.servers.items():
            self._logger.debug(">>{}/udp: {}".format(addr, msg))
            protocol.transport.sendto(("\x08"+msg).encode(), addr)
            return

    def remove_future(self, msg):
        for server, proto in self.servers.items():
            proto.remove_future(msg)
