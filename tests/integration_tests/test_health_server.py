import aiohttp

from tests.utils import fast_forward


@fast_forward(2)
async def test_ready(health_server, lobby_instance):
    url = f"http://{health_server.host}:{health_server.port}/ready"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200

        await lobby_instance.shutdown()

        async with session.get(url) as resp:
            assert resp.status == 503
