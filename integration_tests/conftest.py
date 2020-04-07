import pytest

from .fafclient import FAFClient


@pytest.fixture(scope="function")
async def test_client(request):
    clients = []
    """Create a new client connected to the test server"""
    async def connect(username, password="foo"):
        client = FAFClient()
        clients.append(client)
        await client.connect("test.faforever.com", 8001)
        msg = await client.login(username, password)
        return client, msg

    yield connect

    for client in clients:
        await client.close()
