"""
Forged Alliance Forever server project

Copyright (c) 2014 Gael Honorez
Copyright (c) 2015 Michael Søndergaard <sheeo@sheeo.dk>

Distributed under GPLv3, see license.txt
"""
import json
import server.db
import config

from server.games.game import GameState, VisibilityState
from server.stats.game_stats_service import GameStatsService
from .gameconnection import GameConnection
from .natpacketserver import NatPacketServer
from server.lobbyconnection import LobbyConnection
from server.protocol import Protocol, QDataStreamProtocol
from server.servercontext import ServerContext
from server.player_service import PlayerService
from server.game_service import GameService
from server.control import init as run_control_server

__version__ = '0.1'
__author__ = 'Chris Kitching, Dragonfire, Gael Honorez, Jeroen De Dauw, Crotalus, Michael Søndergaard'
__contact__ = 'admin@faforever.com'
__license__ = 'GPLv3'
__copyright__ = 'Copyright (c) 2011-2015 ' + __author__


__all__ = [
    'run_lobby_server',
    'run_game_server',
    'games',
    'control',
    'abc',
    'protocol'
]


def run_lobby_server(address: (str, int),
                     player_service: PlayerService,
                     games: GameService,
                     loop):
    """
    Run the lobby server

    :param address: Address to listen on
    :param player_service: Service to talk to about players
    :param games: Service to talk to about games
    :param loop: Event loop to use
    :return ServerContext: A server object
    """
    def encode(game):
        # Crazy evil encoding scheme
        return QDataStreamProtocol.pack_block(
            QDataStreamProtocol.pack_qstring(json.dumps(game.to_dict()))
        )

    def report_dirty_games():
        dirties = games.dirty_games
        games.clear_dirty()

        # TODO: This spams squillions of messages: we should implement per-connection message
        # aggregation at the next abstraction layer down :P
        for game in dirties:
            # Don't tell anyone about an ended game.
            # TODO: Probably better to do this at the time of the state transition instead?
            if game.state == GameState.ENDED:
                games.remove_game(game)
                continue

            # So we're going to be broadcasting this to _somebody_...
            message = encode(game)

            # These games shouldn't be broadcast, but instead privately sent to those who are
            # allowed to see them.
            if game.visibility == VisibilityState.FRIENDS:
                # To see this game, you must have an authenticated connection and be a friend of the host.
                validation_func = lambda lobby_conn: lobby_conn.player.id in game.host.friends
            else:
                validation_func = lambda lobby_conn: lobby_conn.player.id not in game.host.foes

            ctx.broadcast_raw(message, lambda lobby_conn: lobby_conn.authenticated and validation_func(lobby_conn))

        loop.call_later(5, report_dirty_games)

    def ping_broadcast():
        ctx.broadcast_raw(QDataStreamProtocol.pack_block(QDataStreamProtocol.pack_qstring('PING')))
        loop.call_later(45, ping_broadcast)

    def initialize_connection():
        return LobbyConnection(context=ctx,
                               games=games,
                               players=player_service,
                               loop=loop)
    ctx = ServerContext(initialize_connection, name="LobbyServer", loop=loop)
    loop.call_later(5, report_dirty_games)
    loop.call_soon(ping_broadcast)
    return ctx.listen(*address)


def run_game_server(address: (str, int),
                    player_service: PlayerService,
                    games: GameService,
                    loop):
    """
    Run the game server

    :return (NatPacketServer, ServerContext): A pair of server objects
    """
    nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT)

    def initialize_connection():
        return GameConnection(loop, player_service, games)
    ctx = ServerContext(initialize_connection, name='GameServer', loop=loop)
    server = ctx.listen(*address)
    return nat_packet_server, server
