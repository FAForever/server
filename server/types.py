from typing import NamedTuple

# Represents a peer IP address
Address = NamedTuple('Address', [('host', str), ('port', int)])
Address.from_string = lambda s: Address(*(s.split(':')))
