import asyncio
from .gameconnection import GameConnection
from .natpacketserver import NatPacketServer

import config


def run_game_server(address, player_service, games, db):
    """
    Start the game server
    """
    loop = asyncio.get_event_loop()
    nat_packet_server = NatPacketServer(loop, config.LOBBY_UDP_PORT)

    def initialize_connection():
        gc = GameConnection(loop, player_service, games, db)
        nat_packet_server.subscribe(gc, ['ProcessServerNatPacket'])
        return gc

    return nat_packet_server, loop.create_server(initialize_connection,
                                                address[0], address[1])
