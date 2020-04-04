import pytest

from .fafclient import FAFClient


@pytest.fixture(scope="session")
def test_client(request):
    """Create a new client connected to the test server"""
    async def connect(username, password="foo"):
        client = FAFClient()
        await client.connect("test.faforever.com", 8001)
        msg = await client.login(username, password)
        return client, msg

    return connect
