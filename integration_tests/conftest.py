import copy
import json

import pytest

from .fafclient import FAFClient


@pytest.fixture(scope="function")
async def client_factory():
    """
    Create new clients connected to the test server and automatically
    disconnect them when the test ends
    """
    class Manager():
        def __init__(self):
            self.clients = []

        async def add_client(self, host="test.faforever.com", port=8002):
            client = FAFClient()
            await client.connect(host, port)
            self.clients.append(client)
            return client

        async def login(self, username, password="foo"):
            client = await self.add_client()
            msg = await client.login(username, password)
            return client, msg

        async def close_all(self):
            for client in self.clients:
                await client.close()

    manager = Manager()
    yield manager
    await manager.close_all()


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
