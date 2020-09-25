import json
from typing import List

import server.metrics as metrics

from ..core import Protocol as _Protocol

json_encoder = json.JSONEncoder(separators=(",", ":"))


class Protocol(_Protocol):
    """For hooking in metric collection"""

    def write_messages(self, messages: List[dict]) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        super().write_messages(messages)

    def write_raw(self, data: bytes) -> None:
        metrics.sent_messages.labels(self.__class__.__name__).inc()
        super().write_raw(data)
