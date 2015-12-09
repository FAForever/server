from typing import NamedTuple, Optional, List
from concurrent.futures import CancelledError, TimeoutError
import asyncio
import logging
from enum import Enum, unique

import config
from server.abc.dispatcher import Dispatcher, Receiver
from server.players import Player
from server.types import Address
from .decorators import with_logger

from server.natpacketserver import NatPacketServer

_natserver = None


async def send_natpacket(addr, msg):
    global _natserver
    if not _natserver:
        _natserver = NatPacketServer()
        await _natserver.listen()
    _natserver.send_natpacket_to(msg, addr)


logger = logging.getLogger(__name__)


@unique
class ConnectivityState(Enum):
    """
    Describes the connectivity level of a peer
    Three levels are defined:
        - PUBLIC:
        The peer is publicly accessible without prior communication
        - STUN:
            The peer must first send an outbound packet
            before being able to receive on the inbound port
        - PROXY:
            The peer is unable to connect by other means than a TCP proxy
    """
    PUBLIC = "PUBLIC"
    STUN = "STUN"
    BLOCKED = "BLOCKED"


ConnectivityResult = NamedTuple('ConnectivityResult', [('addr', Optional[Address]),
                                                       ('state', ConnectivityState)])


@with_logger
class Connectivity(Receiver):
    """
    Processes Nat packets and determines connectivity state of peers.

    Used initially to determine the connectivity state of a player,
    then used while the game lobby is active to establish connections
    between players.
    """
    def __init__(self, dispatcher: Dispatcher, host: str, player: Player):
        self.player = player
        self._result = None
        self._test = None
        self._nat_packets = {}
        self._dispatcher = dispatcher
        self.host = host
        self.relay_address = None
        dispatcher.subscribe_to('connectivity', self)

    @property
    def result(self) -> Optional[ConnectivityResult]:
        return self._result

    async def on_message_received(self, message: dict) -> None:
        cmd, args = message.get('command'), message.get('args', [])
        if cmd == 'ProcessNatPacket':
            self.process_nat_packet(Address.from_string(args[0]), args[1])
        elif cmd == 'InitiateTest':
            asyncio.ensure_future(self.initiate_test(args[0]))
        elif cmd == 'RelayAddress':
            self.relay_address = args[0]

    async def initiate_test(self, port: int):
        self._test = ConnectivityTest(self, self.host, port, self.player)
        result = await self._test.determine_connectivity()
        self._result = result
        self.send('ConnectivityState', [result.state.value,
                                        "{}:{}".format(*result.addr)
                                        if result.addr else ""])

    def send(self, command_id: str, args: Optional[list]=None):
        self._dispatcher.send({
            'command': command_id,
            'target': 'connectivity',
            'args': args or []
        })

    async def ProbePeerNAT(self, peer, use_address=None):
        """
        Instruct self to send an identifiable nat packet to peer

        :return: resolved_address
        """
        assert peer.connectivity.result
        nat_message = "Hello from {}".format(self.player.id)
        addr = peer.connectivity.result.addr if not use_address else use_address
        self._logger.debug("{} probing {} at {} with msg: {}".format(self, peer, addr, nat_message))
        for _ in range(3):
            for i in range(0, 4):
                self._logger.debug("{} sending NAT packet {} to {}".format(self, i, addr))
                ip, port = addr
                self.send('SendNatPacket', ["{}:{}".format(ip, int(port) + i),
                                            nat_message])
        try:
            waiter = self.wait_for_natpacket(nat_message)
            address, message = await asyncio.wait_for(waiter, 4)
            return address
        except (CancelledError, asyncio.TimeoutError):
            return None

    async def wait_for_natpacket(self, message: str, sender: Address=None):
        fut = asyncio.Future()
        self._nat_packets[message] = fut
        self._logger.info("Awaiting nat packet {} from {}".format(message, sender or 'anywhere'))
        addr, msg = await fut
        if fut.done():
            self._logger.info("Received {} from {}".format(msg, addr))
            if (addr == sender or sender is None) and msg == message:
                return addr, msg
        else:
            return False

    async def create_binding(self, peer: 'Connectivity'):
        """
        Create a binding on the relay allocated to 'self'

        Returns the address from which messages coming from 'peer'
        come from
        """
        assert self.result
        assert peer.result
        self.send('CreatePermission', peer.result.addr)
        pkt = 'Bind {}'.format(peer.player.id)
        for i in range(0, 4):
            peer.send_nat_packet(self.relay_address, pkt)
        addr, msg = await self.wait_for_natpacket(pkt)
        return addr

    def process_nat_packet(self, address: Address, message: str):
        self._logger.debug("<<{}: {}".format(address, message))
        if message in self._nat_packets and isinstance(self._nat_packets[message], asyncio.Future):
            if not self._nat_packets[message].done():
                self._nat_packets[message].set_result((address, message))
                del self._nat_packets[message]

    def send_nat_packet(self, address: Address, message: str):
        self._logger.debug(">>{}/udp: {}".format(address, message))
        self.send('SendNatPacket', ["{}:{}".format(*address), message])


@with_logger
class ConnectivityTest:
    """
    Determine the connectivity state of a single peer.
    """

    def __init__(self,
                 connection: Connectivity,
                 host: str,
                 port: int,
                 player: Player):
        """
        :return: None
        """
        super(ConnectivityTest, self).__init__()
        self._connectivity = connection  # type: Connectivity
        self.connectivity_state = None
        self.remote_addr = (host, port)
        self.player = player
        self.identifier = player.id
        self.client_packets = []
        self.server_packets = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    async def determine_connectivity(self):
        """
        Determine connectivity of peer

        :return: Connectivity(addr, ConnectivityState)
        """
        try:
            public = await self.test_public()
            if public:
                return ConnectivityResult(addr=Address(*self.remote_addr), state=ConnectivityState.PUBLIC)
            addr = await self.test_stun()
            if addr:
                return ConnectivityResult(addr=Address(*addr), state=ConnectivityState.STUN)
            else:
                return ConnectivityResult(addr=None, state=ConnectivityState.BLOCKED)
        except (TimeoutError, CancelledError):
            pass
        return ConnectivityResult(addr=None, state=ConnectivityState.BLOCKED)

    async def test_public(self):
        self._logger.debug("Testing PUBLIC")
        message = "Are you public? {}".format(self.identifier)
        received_packet = self._connectivity.wait_for_natpacket(message)
        for i in range(0, 3):
            await send_natpacket(self.remote_addr, message)
        try:
            result = await asyncio.wait_for(received_packet, 1)
            self._logger.info("Result: {}".format(result))
            return True
        except (CancelledError, TimeoutError):
            return False

    async def test_stun(self):
        self._logger.debug("Testing STUN")
        message = "Hello {}".format(self.identifier)
        fut = _natserver.await_packet(message)
        for i in range(0, 3):
            self._connectivity.send('SendNatPacket',
                                    ["%s:%s" % (config.LOBBY_IP,
                                            config.LOBBY_UDP_PORT),
                                     message])
            await asyncio.sleep(0.1)
            try:
                received, addr = await asyncio.wait_for(fut, 0.5)
                if received == message:
                    return addr
            except (CancelledError, TimeoutError):
                pass
