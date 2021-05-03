from aio_pika import DeliveryMode

from .config import config
from .core import Service
from .decorators import with_logger
from .game_service import GameService
from .games import GameState
from .message_queue_service import MessageQueueService
from .player_service import PlayerService
from .timing import LazyIntervalTimer


@with_logger
class BroadcastService(Service):
    """
    Broadcast updates about changed entities.
    """

    def __init__(
        self,
        server: "ServerInstance",
        message_queue_service: MessageQueueService,
        game_service: GameService,
        player_service: PlayerService,
    ):
        self.server = server
        self.message_queue_service = message_queue_service
        self.game_service = game_service
        self.player_service = player_service

    async def initialize(self):
        await self.message_queue_service.declare_exchange(
            config.MQ_EXCHANGE_NAME
        )

        # Using a lazy interval timer so that the intervals can be changed
        # without restarting the server.
        self._broadcast_dirties_timer = LazyIntervalTimer(
            lambda: config.DIRTY_REPORT_INTERVAL,
            self.report_dirties,
            start=True
        )
        self._broadcast_ping_timer = LazyIntervalTimer(
            lambda: config.PING_INTERVAL,
            self.broadcast_ping,
            start=True
        )
        self._logger.debug("Broadcast service initialized")

    async def report_dirties(self):
        self.game_service.update_active_game_metrics()
        dirty_games = self.game_service.pop_dirty_games()
        dirty_queues = self.game_service.pop_dirty_queues()
        dirty_players = self.player_service.pop_dirty_players()

        if dirty_queues:
            matchmaker_info = {
                "command": "matchmaker_info",
                "queues": [queue.to_dict() for queue in dirty_queues]
            }
            self.server.write_broadcast(matchmaker_info)

        if dirty_players:
            player_info = {
                "command": "player_info",
                "players": [player.to_dict() for player in dirty_players]
            }
            self.server.write_broadcast(player_info)

        game_info = {
            "command": "game_info",
            "games": []
        }
        # TODO: This spams squillions of messages: we should implement per-
        # connection message aggregation at the next abstraction layer down :P
        for game in dirty_games:
            if game.state == GameState.ENDED:
                self.game_service.remove_game(game)

            # So we're going to be broadcasting this to _somebody_...
            message = game.to_dict()
            game_info["games"].append(message)

            self.server.write_broadcast(
                message,
                lambda conn: (
                    conn.authenticated
                    and game.is_visible_to_player(conn.player)
                )
            )

        if dirty_queues:
            await self.message_queue_service.publish(
                config.MQ_EXCHANGE_NAME,
                "broadcast.matchmakerInfo.update",
                matchmaker_info,
                delivery_mode=DeliveryMode.NOT_PERSISTENT
            )

        if dirty_players:
            await self.message_queue_service.publish(
                config.MQ_EXCHANGE_NAME,
                "broadcast.playerInfo.update",
                player_info,
                delivery_mode=DeliveryMode.NOT_PERSISTENT
            )

        if dirty_games:
            await self.message_queue_service.publish(
                config.MQ_EXCHANGE_NAME,
                "broadcast.gameInfo.update",
                game_info,
                delivery_mode=DeliveryMode.NOT_PERSISTENT
            )

    def broadcast_ping(self):
        self.server.write_broadcast({"command": "ping"})
