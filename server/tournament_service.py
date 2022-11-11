import asyncio
import datetime
import json

import aio_pika

from server import games, metrics
from server.config import config

from .core import Service
from .decorators import with_logger
from .exceptions import ClientError
from .game_service import GameService
from .games import InitMode
from .games.ladder_game import GameClosedError
from .ladder_service.ladder_service import LadderService, NotConnectedError
from .message_queue_service import MessageQueueService
from .player_service import PlayerService
from .players import Player, PlayerState
from .timing import at_interval, datetime_now
from .tournaments.tournament_game import TournamentGameInfo, TournamentGameState
from .types import GameLaunchOptions


def _notify_players(game: TournamentGameInfo):
    for player in game:
        player.state = PlayerState.STARTING_TOURNAMENT
        player.write_message(
            {
                "command": "is_ready",
                "featured_mod": game.featured_mod,
                "request_id": game.request_id,
                "response_time_seconds": game.response_time_seconds,
                "game_name": game.name
            }
        )
    game.state = TournamentGameState.CONFIRMATION_PENDING


@with_logger
class TournamentService(Service):
    """
    Service responsible for managing the tournament or galactic war games.
    """

    def __init__(self, game_service: GameService, message_queue_service: MessageQueueService,
                 player_service: PlayerService, ladder_service: LadderService):
        self._update_task = None
        self.game_service = game_service
        self.ladder_service = ladder_service
        self.player_service = player_service
        self.message_queue_service = message_queue_service
        self._games: set[TournamentGameInfo] = set()

    async def initialize(self):
        self._update_task = at_interval(5, self.update_dirties)
        await self.message_queue_service.listen_to_message("faf-lobby.tourneylauncher.createGame",
                                                           "request.match.create", self._create_game)

    async def shutdown(self):
        self._update_task.stop()

    async def update_dirties(self):
        await self._check_for_timed_out_games()

    async def _check_for_timed_out_games(self):
        for game in self._games.copy():
            if game.state == TournamentGameState.CONFIRMATION_PENDING and game.is_confirmation_overdue():
                self._logger.info("Ready responses from players missing, canceling tournament game %s", game.request_id)
                game.players_causing_cancel = set(player.id for player in game.players) - game.players_ready_ids
                game.state = TournamentGameState.PLAYER_NOT_CONFIRMING
                await self._remove_and_cancel_game(game)
                return
            if game.state.is_done():
                self._games.remove(game)
                return
            if (datetime_now() - game.created_time).hours > 10:
                self._games.remove(game)
                self._logger.warning("Deleting leaked game with id: %s", game.request_id)

    async def _remove_and_cancel_game(self, game: TournamentGameInfo, make_idle=True):
        for player in game.players:
            player.write_message({
                "command": "match_cancelled",
            })
        self._games.remove(game)
        if make_idle:
            for player in game.players:
                player.state = PlayerState.IDLE
        await self.message_queue_service.publish(
            config.MQ_EXCHANGE_NAME,
            "tourneylauncher.createGame.failed",
            {
                "error_code": game.get_error_code(),
                "players_causing_cancel": game.players_causing_cancel
            },
            correlation_id=game.request_id
        )
        metrics.matches_tournament.labels("failed").inc()

    async def _game_created(self, game: games.TournamentGame, tournament_game: TournamentGameInfo):
        tournament_game.state = TournamentGameState.RUNNING
        self._games.remove(tournament_game)
        await self.message_queue_service.publish(
            config.MQ_EXCHANGE_NAME,
            "tourneylauncher.createGame.success",
            {
                "game_id": game.id
            },
            correlation_id=tournament_game.request_id
        )
        metrics.matches_tournament.labels("success").inc()

    async def _create_game(self, message: aio_pika.abc.AbstractIncomingMessage):
        metrics.matches_tournament.labels("requested").inc()
        try:
            self._logger.info("Received Tournament game message")
            await self._process_create_game(message)
        except Exception:
            self._logger.exception("Unknown failure creating tournament game")
            await self.message_queue_service.publish(
                config.MQ_EXCHANGE_NAME,
                "tourneylauncher.createGame.failed",
                {
                    "request_id": message.correlation_id,
                    "error_code": "OTHER"
                },
            )

    async def _process_create_game(self, message):
        body = message.body
        body = json.loads(body)
        game = TournamentGameInfo(**body)
        assert game.request_id == message.correlation_id
        if not await self._fetch_players(game):
            await self._remove_and_cancel_game(game, make_idle=False)
            return
        _notify_players(game)

    async def _fetch_players(self, game):
        if not game.participants:
            self._logger.warning("Tournament game requested with empty player list")
            return False
        await self.add_tournament_game(game)
        for participant in game.participants:
            player_id = participant["player_id"]
            player = self.player_service[player_id]
            if player is None:
                self._logger.warning("Tournament game requested with player id(%s) that could not be found", player_id)
                game.state = TournamentGameState.PLAYER_NOT_ONLINE
                game.players_causing_cancel.add(player_id)
                continue
            if not player.state == PlayerState.IDLE:
                self._logger.warning("Tournament game requested with player id(%s), player not idle", player_id)
                game.state = TournamentGameState.PLAYER_NOT_IDLE
                game.players_causing_cancel.add(player_id)
            game.players.append(player)
        return game.state == TournamentGameState.SCHEDULED

    async def add_tournament_game(self, game):
        self._games.add(game)

    async def on_is_ready_response(self, message, player):
        game = await self._get_game_for_request_id(message["request_id"])
        if game is None:
            raise ClientError("You try to ready up for a game that does not exist")
        if game.state != TournamentGameState.CONFIRMATION_PENDING:
            raise ClientError("You try to ready up for a game that is not waiting for confirmation")
        if player not in game:
            raise ClientError("You try to ready up for a game that you are not in")
        if player.id in game.players_ready_ids:
            return
        await self.add_player_to_ready_list(game, player)

    async def add_player_to_ready_list(self, game, player):
        game.players_ready_ids.add(player.id)
        if game.is_ready():
            await self._launch(game)

    async def _get_game_for_request_id(self, request_id) -> TournamentGameInfo:
        for game in self._games.copy():
            if game.request_id == request_id:
                return game

    async def _launch(self, tournament_game: TournamentGameInfo):
        tournament_game.state = TournamentGameState.STARTING
        self._logger.debug(
            "Starting %s game with",
            tournament_game.name
        )
        game = None
        try:
            host = tournament_game.players[0]
            all_players = tournament_game.players
            all_guests = all_players[1:]

            game = self.game_service.create_game(
                game_class=games.tournament_game.TournamentGame,
                game_mode=tournament_game.featured_mod,
                host=host,
                name="Matchmaker Game",
                max_players=len(all_players),
                map_name=tournament_game.map_name
            )
            game.init_mode = InitMode.AUTO_LOBBY
            game.set_name_unchecked(tournament_game.name)

            for player in all_players:
                player.state = PlayerState.STARTING_AUTOMATCH
            for player in all_players:
                # FA uses lua and lua arrays are 1-indexed
                slot = tournament_game.get_slot_of_player(player)
                # 2 if even, 3 if odd
                team = tournament_game.get_team_of_player(player)
                player.game = game

                # Set player options without triggering the logic for
                # determining that players have actually connected to the game.
                game._player_options[player.id]["Faction"] = tournament_game.get_faction_of_player(player)
                game._player_options[player.id]["Team"] = team
                game._player_options[player.id]["StartSpot"] = slot
                game._player_options[player.id]["Army"] = slot
                game._player_options[player.id]["Color"] = slot

            game_options = tournament_game.game_options
            if game_options:
                game.gameOptions.update(game_options)

            self._logger.debug("Starting tournament game: %s", game)

            def make_game_options(player: Player) -> GameLaunchOptions:
                return GameLaunchOptions(
                    mapname=tournament_game.map_name,
                    expected_players=len(all_players),
                    game_options=game_options,
                    team=game.get_player_option(player.id, "Team"),
                    faction=game.get_player_option(player.id, "Faction"),
                    map_position=game.get_player_option(player.id, "StartSpot")
                )

            await self.ladder_service.launch_server_made_game(game, host, all_guests, make_game_options)
            self._logger.debug("Tournament game launched successfully %s", game)
            await self._game_created(game, tournament_game)
        except Exception as e:
            abandoning_players = []
            if isinstance(e, NotConnectedError):
                self._logger.info(
                    "Tournament game failed to start! %s setup timed out",
                    game
                )
                # TODO: metrics.matches.labels(queue.name, MatchLaunch.TIMED_OUT).inc()
                abandoning_players = e.players
                tournament_game.state = TournamentGameState.PLAYER_NOT_ONLINE
            elif isinstance(e, GameClosedError):
                self._logger.info(
                    "Tournament game %s failed to start! "
                    "Player %s closed their game instance",
                    game, e.player
                )
                # TODO: metrics.matches.labels(queue.name, MatchLaunch.ABORTED_BY_PLAYER).inc()
                abandoning_players = [e.player]
                tournament_game.state = TournamentGameState.PLAYER_NOT_STARTING
            else:
                # All timeout errors should be transformed by the match starter.
                assert not isinstance(e, asyncio.TimeoutError)

                self._logger.exception("Tournament game failed to start %s", game)
                # TODO: metrics.matches.labels(queue.name, MatchLaunch.ERRORED).inc()
                tournament_game.state = TournamentGameState.PLAYER_NOT_CONNECTING
            if game:
                await game.on_game_finish()

            if abandoning_players:
                self._logger.info(
                    "Players failed to connect: %s",
                    abandoning_players
                )
                tournament_game.players_causing_cancel = set([player.id for player in abandoning_players])
            await self._remove_and_cancel_game(tournament_game)
