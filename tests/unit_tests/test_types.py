from server.types import Address, NeroxisGeneratedMap


def test_address_from_string():
    address = Address.from_string("localhost:4000")

    assert address == Address("localhost", 4000)


def test_address_from_string_with_scheme():
    address = Address.from_string("http://localhost:4000")

    assert address == Address("http://localhost", 4000)


def test_is_neroxis_map():
    assert NeroxisGeneratedMap.is_neroxis_map(
        "neroxis_map_generator_1.13.0_htvbrglnjszew_baeaeaa_aaaaaadhlwmjq",
    ) is True
    assert NeroxisGeneratedMap.is_neroxis_map(
        "neroxis_map_generator_1.13.0_zxgxph43rfbj4_aycaeaa_aaaaaadhlwuas",
    ) is True
    assert NeroxisGeneratedMap.is_neroxis_map(
        "neroxis_map_generator_1.13.0_avkycu6ce63e2_baeaeaa_aaaaaadhlxdhe",
    ) is True
