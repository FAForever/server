import pytest

from .conftest import connect_and_sign_in, read_until_command

pytestmark = pytest.mark.asyncio


async def test_modvault_start(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until_command(proto, 'game_info')

    await proto.send_message({
        'command': 'modvault',
        'type': 'start'
    })

    # Make sure all 5 mod version messages are sent
    for _ in range(5):
        await read_until_command(proto, 'modvault_info')


async def test_modvault_like(lobby_server):
    _, _, proto = await connect_and_sign_in(
        ('test', 'test_password'),
        lobby_server
    )

    await read_until_command(proto, 'game_info')

    await proto.send_message({
        'command': 'modvault',
        'type': 'like',
        'uid': 'FFF'
    })

    msg = await read_until_command(proto, 'modvault_info')
    # Not going to verify the date
    del msg['date']

    assert msg == {
        'command': 'modvault_info',
        'thumbnail': '',
        'link': 'http://content.faforever.com/faf/vault/noicon.zip',
        'bugreports': [],
        'comments': [],
        'description': 'The best version so far',
        'played': 0,
        'likes': 1.0,
        'downloads': 0,
        'uid': 'FFF',
        'name': 'Mod without icon',
        'version': 1,
        'author': 'foo',
        'ui': 1
    }
