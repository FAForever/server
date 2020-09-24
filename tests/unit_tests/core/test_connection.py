import mock
import pytest

from server.core import RouteError
from server.core.connection import Connection, handler


@pytest.mark.asyncio
async def test_basic():
    foo = mock.Mock()
    bar = mock.Mock()

    class TestConnection(Connection):
        @handler("foo")
        async def handle_foo(self, message):
            foo(message)

        @handler("bar")
        async def handle_bar(self, message):
            bar(message)

    conn = TestConnection(mock.Mock(), mock.Mock())

    # Static dispatch
    await conn.handle_foo({"command": "foo"})
    foo.assert_called_once_with({"command": "foo"})
    await conn.handle_bar({"command": "bar"})
    bar.assert_called_once_with({"command": "bar"})

    foo.reset_mock()
    bar.reset_mock()

    # Dynamic dispatch
    await conn.on_message_received({"command": "foo"})
    foo.assert_called_once_with({"command": "foo"})
    await conn.on_message_received({"command": "bar"})
    bar.assert_called_once_with({"command": "bar"})


@pytest.mark.asyncio
async def test_inheritance():
    foo = mock.Mock()
    bar = mock.Mock()
    foo2 = mock.Mock()
    baz = mock.Mock()

    class Base(Connection):
        @handler("foo")
        async def handle_foo(self, message):
            foo(message)

        @handler("bar")
        async def handle_bar(self, message):
            bar(message)

    class Child(Base):
        @handler("foo")
        async def handle_foo_2(self, message):
            foo2(message)

        @handler("baz")
        async def handle_baz(self, message):
            baz(message)

    base = Base(mock.Mock(), mock.Mock())
    child = Child(mock.Mock(), mock.Mock())

    await base.on_message_received({"command": "foo"})
    foo.assert_called_once_with({"command": "foo"})
    foo2.assert_not_called()
    foo.reset_mock()

    await child.on_message_received({"command": "foo"})
    foo.assert_not_called()
    foo2.assert_called_once_with({"command": "foo"})

    await base.on_message_received({"command": "bar"})
    bar.assert_called_once_with({"command": "bar"})
    bar.reset_mock()

    await child.on_message_received({"command": "bar"})
    bar.assert_called_once_with({"command": "bar"})

    with pytest.raises(RouteError):
        await base.on_message_received({"command": "baz"})
    baz.assert_not_called()

    await child.on_message_received({"command": "baz"})
    baz.assert_called_once_with({"command": "baz"})
