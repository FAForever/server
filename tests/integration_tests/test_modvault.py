from .conftest import connect_and_sign_in, read_until_command


async def test_modvault_start(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until_command(proto, 'game_info')

    proto.send_message({
        'command': 'modvault',
        'type': 'start',
        'faction': 'uef'
    })
    await proto.drain()

    # Make sure all 5 mod version messages are sent
    for _ in range(5):
        await read_until_command(proto, 'modvault_info')
