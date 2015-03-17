import asyncio
import socket
import mock
from src.natpacketserver import NatPacketServer

import logging

@asyncio.coroutine
def test_NatPacketServer_receives_udp(loop):
    with NatPacketServer(loop, 12345) as s:
        receiver = mock.Mock()
        yield from asyncio.sleep(0.1)
        with s.subscribe(receiver, ['ProcessServerNatPacket']) as sub:
            writer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            writer.connect(('127.0.0.1', 12345))
            logging.debug("Sending message")
            writer.sendall('\x08{}'.format("Test").encode())
            yield from sub.wait_for('ProcessServerNatPacket', 2)
            receiver.handle_ProcessServerNatPacket.assert_any_call(mock.ANY)
            writer.close()
            logging.debug("Test done")
