import pytest

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("username", (
    "test",
    "test2"
))
async def test_user_existence(client_factory, username):
    """Verify that these users exist on the test server"""
    client, welcome_message = await client_factory.login(username, "foo")

    assert welcome_message["me"]["login"] == username
    assert client.is_connected()
