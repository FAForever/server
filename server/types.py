from typing import NamedTuple


class Address(NamedTuple):
    """A peer IP address"""

    host: str
    port: int

    @classmethod
    def from_string(cls, s: str) -> "Address":
        host, port = s.split(":")
        return cls(host, int(port))
