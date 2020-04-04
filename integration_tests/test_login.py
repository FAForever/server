import pytest

# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("username", (
    "test",
    "test2"
))
async def test_user_existence(test_client, username):
    """Verify that these users exist on the test server"""
    client, welcome_message = await test_client(username, "foo")

    assert welcome_message["login"] == welcome_message["me"]["login"] == username
    assert welcome_message["id"] == welcome_message["me"]["id"]
    assert client.is_connected()
