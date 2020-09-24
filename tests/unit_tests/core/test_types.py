from server.core.typedefs import Address


def test_address_from_string():
    address = Address.from_string("localhost:4000")

    assert address == Address("localhost", 4000)


def test_address_from_string_with_scheme():
    address = Address.from_string("http://localhost:4000")

    assert address == Address("http://localhost", 4000)
