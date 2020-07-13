import json

from .protocol import Protocol, json_encoder


class SimpleJsonProtocol(Protocol):
    @staticmethod
    def encode_message(message: dict) -> bytes:
        return (json_encoder.encode(message) + "\n").encode()

    async def read_message(self) -> dict:
        line = await self.reader.readline()
        return json.loads(line.strip())
