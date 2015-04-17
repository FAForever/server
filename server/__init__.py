import asyncio
from .gameconnection import GameConnection
from .natpacketserver import NatPacketServer

import config
from server.servercontext import ServerContext


def run_game_server(address, player_service, games, db, loop=asyncio.get_event_loop()):
    """
    Start the game server
    :param (str, int) address: (host, port) tuple to listen on
    """
    nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT)

    def initialize_connection(protocol):
        print('Initialize connection')
        gc = GameConnection(loop, player_service, games, db)
        gc.on_connection_made(protocol, protocol.writer.get_extra_info('peername'))
        nat_packet_server.subscribe(gc, ['ProcessServerNatPacket'])
        return gc
    ctx = ServerContext(initialize_connection, loop)
    server = ctx.listen(address[0], address[1])
    return nat_packet_server, server
