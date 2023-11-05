
async def test_ping(client_factory):
    client = await client_factory.add_client()

    await client.ping()
    await client.read_until_command("pong", timeout=5)


async def test_matchmaker_info(client_factory):
    client, _ = await client_factory.login("test")

    await client.send_command("matchmaker_info")
    msg = await client.read_until_command("matchmaker_info")

    assert msg["queues"]
    for queue in msg["queues"]:
        assert queue["queue_name"]
        assert queue["queue_pop_time"]
        assert "num_players" in queue
