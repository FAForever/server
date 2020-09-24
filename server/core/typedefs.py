from typing import Any, Callable, Dict, NamedTuple

# Type aliases
Handler = Callable[..., Any]
Message = Dict[Any, Any]


# Named tuples
class Address(NamedTuple):
    """A peer IP address"""

    host: str
    port: int

    @classmethod
    def from_string(cls, address: str) -> "Address":
        host, port = address.rsplit(":", 1)
        return cls(host, int(port))
