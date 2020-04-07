import copy
import json

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


@pytest.fixture(scope="session")
def json_stats_1v1():
    with open("tests/data/game_stats_simple_win.json") as f:
        stats = f.read()
    stats = json.loads(stats)

    def make_stats(name1, name2):
        new_stats = copy.deepcopy(stats)
        new_stats["stats"][0]["name"] = name1
        new_stats["stats"][1]["name"] = name2
        return json.dumps(new_stats)

    return make_stats
