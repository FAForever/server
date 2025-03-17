r"""A simple newline terminated JSON data format.

# Example:
```python
>>> SimpleJsonProtocol.encode_message({"command": "ping"})
b'{"command":"ping"}\n'

```
"""

import json
from collections.abc import Mapping
from typing import Any

from .protocol import DisconnectedError, Protocol, json_encoder


class SimpleJsonProtocol(Protocol):
    @staticmethod
    def encode_message(message: Mapping[str, Any]) -> bytes:
        return (json_encoder.encode(message) + "\n").encode()

    @staticmethod
    def decode_message(data: bytes) -> dict[str, Any]:
        return json.loads(data.strip())

    async def read_message(self) -> dict[str, Any]:
        line = await self.reader.readline()
        if not line:
            raise DisconnectedError()
        return SimpleJsonProtocol.decode_message(line)
