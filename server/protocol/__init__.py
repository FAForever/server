"""
Protocol format definitions

Every message sent between the lobby server and a client is expected to
deserialize to a python dictionary. The structure of that dictionary depends on
the application logic (see `server.lobbyconnection`).

This module defines the classes that handle the wire format, i.e. how messages
are serialized to bytes and sent across the network.
"""

from .gpgnet import GpgNetClientProtocol, GpgNetServerProtocol
from .protocol import DisconnectedError, Protocol
from .qdatastream import QDataStreamProtocol
from .simple_json import SimpleJsonProtocol

__all__ = (
    "DisconnectedError",
    "GpgNetClientProtocol",
    "GpgNetServerProtocol",
    "Protocol",
    "QDataStreamProtocol",
    "SimpleJsonProtocol"
)
