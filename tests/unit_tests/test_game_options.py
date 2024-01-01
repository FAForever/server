import asyncio
import pathlib
from unittest import mock

import pytest

from server.games import GameOptions, Victory


@pytest.fixture
def game_options() -> GameOptions:
    return GameOptions(0)


def test_type_transformations(game_options):
    game_options["Victory"] = "sandbox"
    assert game_options["Victory"] is Victory.SANDBOX

    game_options["Slots"] = "10"
    assert game_options["Slots"] == 10

    game_options["ScenarioFile"] = "/maps/map_name/map_name_scenario.lua"
    assert game_options["ScenarioFile"] == pathlib.PurePath(
        "/maps/map_name/map_name_scenario.lua"
    )


def test_type_transformations_invalid(game_options, caplog):
    with caplog.at_level("WARNING"):
        game_options["Victory"] = "invalid"

    assert "Invalid victory type 'invalid'! Using 'None' instead." in caplog.messages
    assert "Victory" not in game_options

    with pytest.raises(ValueError):
        game_options["Slots"] = "foobar"

    assert "Slots" not in game_options


async def test_callbacks(game_options):
    callback = mock.Mock()
    callback2 = mock.Mock()
    async_callback = mock.AsyncMock()

    game_options.add_callback("OneCallback", callback)
    game_options.add_callback("ManyCallbacks", callback)
    game_options.add_callback("ManyCallbacks", callback2)
    game_options.add_async_callback("ManyCallbacks", async_callback)

    game_options["OneCallback"] = "Some Value"
    callback.assert_called_once_with("Some Value")

    game_options["ManyCallbacks"] = "Another Value"
    callback.assert_called_with("Another Value")
    callback2.assert_called_once_with("Another Value")
    async_callback.assert_called_once_with("Another Value")

    async_callback.assert_not_awaited()
    await asyncio.sleep(0)
    async_callback.assert_awaited_once_with("Another Value")


async def test_await_callbacks(game_options):
    callback = mock.Mock()
    callback2 = mock.Mock()
    async_callback = mock.AsyncMock()

    game_options.add_callback("OneCallback", callback)
    game_options.add_callback("ManyCallbacks", callback)
    game_options.add_callback("ManyCallbacks", callback2)
    game_options.add_async_callback("ManyCallbacks", async_callback)

    await game_options.set_option("OneCallback", "Some Value")
    callback.assert_called_once_with("Some Value")

    await game_options.set_option("ManyCallbacks", "Another Value")
    callback.assert_called_with("Another Value")
    callback2.assert_called_once_with("Another Value")
    async_callback.assert_awaited_once_with("Another Value")


async def test_callback_error(game_options, caplog):
    callback = mock.Mock()
    async_callback = mock.AsyncMock()

    def raises_error(_):
        raise RuntimeError("test")

    game_options.add_callback("Foo", raises_error)
    game_options.add_callback("Foo", callback)
    game_options.add_async_callback("Foo", async_callback)

    with caplog.at_level("TRACE"):
        game_options["Foo"] = "Some Value"

    callback.assert_called_once_with("Some Value")
    async_callback.assert_called_once_with("Some Value")
    assert "Error running callback for 'Foo' (value 'Some Value')" in caplog.messages


async def test_async_callback_error(game_options, caplog):
    callback = mock.Mock()
    async_callback = mock.AsyncMock()

    async def async_raises_error(_):
        raise RuntimeError("test")

    game_options.add_callback("Foo", callback)
    game_options.add_async_callback("Foo", async_raises_error)
    game_options.add_async_callback("Foo", async_callback)

    with caplog.at_level("TRACE"):
        game_options["Foo"] = "Some Value"
        await asyncio.sleep(0)

    callback.assert_called_once_with("Some Value")
    async_callback.assert_called_once_with("Some Value")
    assert "Error running async callback for 'Foo' (value 'Some Value')" in caplog.messages
