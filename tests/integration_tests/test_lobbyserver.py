import asyncio
import aiomysql
from unittest import mock
import pytest
from server import run_lobby_server, GamesService, PlayersOnline
from server.protocol import QDataStreamProtocol

@pytest.fixture
def lobby_server(request, loop, db_pool, mock_players, mock_games, db):
    server = loop.run_until_complete(run_lobby_server(('127.0.0.1', None),
                                                      mock_players,
                                                      mock_games,
                                                      db,
                                                      db_pool,
                                                      loop))

    def fin():
        server.close()
        loop.run_until_complete(server.wait_closed())
    request.addfinalizer(fin)

    return server

@asyncio.coroutine
def test_server_listen(loop, mock_players, mock_games, db, mock_db_pool):
    with mock.patch('server.lobbyconnection.QSqlQuery') as query:
        server = yield from run_lobby_server(('127.0.0.1', None),
                                              mock_players,
                                              mock_games,
                                              db,
                                              db_pool=mock_db_pool,
                                              loop=loop)
        (reader, writer) = yield from asyncio.open_connection(*server.sockets[0].getsockname())
        proto = QDataStreamProtocol(reader, writer)
        proto.send_message({'command': 'hello',
                            'version': 0,
                            'login': 'Cat',
                            'password': 'epic',
                            'unique_id': 'some_id'})
        yield from writer.drain()
        msg = yield from proto.read_message()
        assert msg == {'command': 'notice',
                       'style': 'error',
                       'text': 'Login not found or password incorrect. They are case sensitive.'}
        server.close()
        writer.close()
        yield from server.wait_closed()
