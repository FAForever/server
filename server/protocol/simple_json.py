import json

from .protocol import DisconnectedError, Protocol, json_encoder


class SimpleJsonProtocol(Protocol):
    @staticmethod
    def encode_message(message: dict) -> bytes:
        return (json_encoder.encode(message) + "\n").encode()

    @staticmethod
    def decode_message(data: bytes) -> dict:
        return json.loads(data.strip())

    async def read_message(self) -> dict:
        line = await self.reader.readline()
        if not line:
            raise DisconnectedError()
        return SimpleJsonProtocol.decode_message(line)
