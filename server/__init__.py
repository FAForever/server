import asyncio
from asyncio import AbstractEventLoop
import ujson
from .gameconnection import GameConnection
from .natpacketserver import NatPacketServer

import config
from server.games import GamesContainer, Ladder1V1GamesContainer
from server.games.coopGamesContainer import CoopGamesContainer
from server.lobbyconnection import LobbyConnection
from server.protocol import QDataStreamProtocol
from server.servercontext import ServerContext
from server.players import PlayersOnline
from server.games_service import GamesService


def run_lobby_server(address: (str, int),
                     player_service: PlayersOnline,
                     games: GamesService,
                     db,
                     loop: AbstractEventLoop=asyncio.get_event_loop()):
    """
    Run the lobby server

    :param address: Address to listen on
    :param player_service: Service to talk to about players
    :param games: Service to talk to about games
    :param db: Database
    :param loop: Event loop to use
    :return ServerContext: A server object
    """
    def report_dirty_games():
        dirties = games.dirty_games
        def encode(game):
            return QDataStreamProtocol.pack_block(
                QDataStreamProtocol.pack_qstring(ujson.dumps(game.to_dict()))
            )
        message = b''.join(map(encode, dirties))
        if len(message) > 0:
            ctx.broadcast_raw(message, validate_fn=lambda lobby_conn: lobby_conn.loginDone)
        loop.call_later(5, report_dirty_games)
    def initialize_connection(protocol):
        conn = LobbyConnection(context=ctx,
                               games=games,
                               players=player_service,
                               db=db,
                               loop=loop)
        conn.on_connection_made(protocol, protocol.writer.get_extra_info('peername'))
        return conn
    ctx = ServerContext(initialize_connection, name="LobbyServer", loop=loop)
    loop.call_later(5, report_dirty_games)
    return ctx.listen(*address)


def run_game_server(address: (str, int),
                    player_service: PlayersOnline,
                    games: GamesService,
                    db,
                    loop: AbstractEventLoop=asyncio.get_event_loop()):
    """
    Run the game server

    :return (NatPacketServer, ServerContext): A pair of server objects
    """
    nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT)

    def initialize_connection(protocol):
        gc = GameConnection(loop, player_service, games, db)
        gc.on_connection_made(protocol, protocol.writer.get_extra_info('peername'))
        nat_packet_server.subscribe(gc, ['ProcessServerNatPacket'])
        return gc
    ctx = ServerContext(initialize_connection, name='GameServer', loop=loop)
    server = ctx.listen(*address)
    return nat_packet_server, server
