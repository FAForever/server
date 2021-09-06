import json

from .protocol import DisconnectedError, Protocol, json_encoder


class SimpleJsonProtocol(Protocol):
    @staticmethod
    def encode_message(message: dict) -> bytes:
        return (json_encoder.encode(message) + "\n").encode()

    async def read_message(self) -> dict:
        line = await self.reader.readline()
        if not line:
            raise DisconnectedError()
        return json.loads(line.strip())
