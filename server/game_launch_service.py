"""
Launches games whose players and settings were decided by another service.

The lobby server owns the game client of every player, so it is the only place
that can safely put players into a game. Services that decide who should play
(the matchmaker, and in the future e.g. Galactic War) describe the game with a
`MatchSpec` and hand it to `GameLaunchService.create_match`, which answers with
a `MatchLaunchResult`.

Both types only contain plain data, so that the same contract can be exposed
over the message queue (`request.match.create`) once matchmaking moves out of
the lobby server.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum, unique
from typing import Any, ClassVar, Optional

from server.core import Service
from server.decorators import with_logger
from server.game_service import GameService
from server.games import InitMode, LadderGame
from server.games.ladder_game import GameClosedError
from server.player_service import PlayerService
from server.players import Player, PlayerState
from server.types import GameLaunchOptions, Map


@dataclass(frozen=True)
class MatchPlayer:
    """A player's seat in a match."""

    player_id: int
    # FA team number. Team 1 means 'no team', so real teams start at 2
    team: int
    # 1-indexed lobby slot, used as start spot, army and color
    slot: int
    faction: int


@dataclass(frozen=True)
class MatchSpec:
    """Everything needed to set up a match that was decided elsewhere."""

    name: str
    featured_mod: str
    rating_type: str
    map: Map
    host_id: int
    players: tuple[MatchPlayer, ...]
    matchmaker_queue_id: Optional[int] = None
    game_options: Optional[dict[str, Any]] = None


@unique
class LaunchFailureReason(Enum):
    """Why a player kept a match from launching."""

    # Rejected before a game was created
    OFFLINE = "offline"
    BUSY = "busy"
    # The game was created, but the player did not make it into the game
    NOT_CONNECTED = "not_connected"
    ABORTED = "aborted"


@dataclass(frozen=True)
class PlayerLaunchFailure:
    """A player that kept a match from launching."""

    player_id: int
    reason: LaunchFailureReason


@dataclass(frozen=True)
class MatchLaunchResult:
    """Answer to a `MatchSpec`."""

    # Set as soon as a game was created, even if it failed to launch
    game_id: Optional[int] = None
    failed_players: tuple[PlayerLaunchFailure, ...] = ()
    # Set if the launch failed for a reason that no player is responsible for
    error: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        """Whether the match was launched."""
        return not self.failed_players and self.error is None

    def failed_player_ids(self, *reasons: LaunchFailureReason) -> set[int]:
        """Get the players that failed for any of `reasons`, or for any reason."""
        return {
            failure.player_id
            for failure in self.failed_players
            if not reasons or failure.reason in reasons
        }


class NotConnectedError(asyncio.TimeoutError):
    """Some players did not connect to the match in time."""

    def __init__(self, players: list[Player]):
        """Remember which players failed to connect."""
        self.players = players


@with_logger
class GameLaunchService(Service):
    """Puts players into games that were set up by other services."""

    _logger: ClassVar[logging.Logger]

    def __init__(
        self,
        game_service: GameService,
        player_service: PlayerService,
    ):
        """Create the service."""
        self.game_service = game_service
        self.player_service = player_service

    async def create_match(self, spec: MatchSpec) -> MatchLaunchResult:
        """Create the game described by `spec` and launch it for everyone."""
        # Returns once the game has launched or the launch has failed. Players
        # are only accepted if they are online and not in a game. They are
        # claimed before the first `await`, so the check can not go stale.
        player_ids = [match_player.player_id for match_player in spec.players]
        if (
            len(set(player_ids)) != len(player_ids)
            or spec.host_id not in player_ids
        ):
            self._logger.warning("Rejecting invalid match spec: %s", spec)
            return MatchLaunchResult(error="invalid match spec")

        players: dict[int, Player] = {}
        unavailable: list[PlayerLaunchFailure] = []
        for match_player in spec.players:
            player = self.player_service.get_player(match_player.player_id)
            if player is None or player.lobby_connection is None:
                unavailable.append(PlayerLaunchFailure(
                    match_player.player_id, LaunchFailureReason.OFFLINE
                ))
            elif player.state is not PlayerState.IDLE:
                unavailable.append(PlayerLaunchFailure(
                    match_player.player_id, LaunchFailureReason.BUSY
                ))
            else:
                players[player.id] = player

        if unavailable:
            self._logger.info(
                "Rejecting match %s, players are unavailable: %s",
                spec.name,
                unavailable
            )
            return MatchLaunchResult(failed_players=tuple(unavailable))

        for player in players.values():
            player.state = PlayerState.STARTING_AUTOMATCH

        game = None
        try:
            game = self._create_game(spec, players)
            await self._launch_game(game, spec, players)
            return MatchLaunchResult(game_id=game.id)
        except Exception as e:
            result = self._make_failure_result(e, game)

        if game:
            await game.on_game_finish()
        self._release_unlaunched_players(players.values())

        return result

    def _create_game(
        self,
        spec: MatchSpec,
        players: dict[int, Player]
    ) -> LadderGame:
        game = self.game_service.create_game(
            game_class=LadderGame,
            game_mode=spec.featured_mod,
            host=players[spec.host_id],
            name="Matchmaker Game",
            map=spec.map,
            matchmaker_queue_id=spec.matchmaker_queue_id,
            rating_type=spec.rating_type,
            max_players=len(spec.players),
        )
        game.init_mode = InitMode.AUTO_LOBBY
        game.set_name_unchecked(spec.name)

        for match_player in spec.players:
            player = players[match_player.player_id]
            player.game = game

            # Set player options without triggering the logic for
            # determining that players have actually connected to the game.
            options = game._player_options[player.id]
            options["Faction"] = match_player.faction
            options["Team"] = match_player.team
            options["StartSpot"] = match_player.slot
            options["Army"] = match_player.slot
            options["Color"] = match_player.slot

        if spec.game_options:
            game.game_options.update(spec.game_options)

        self._logger.debug("Created match: %s", game)
        return game

    async def _launch_game(
        self,
        game: LadderGame,
        spec: MatchSpec,
        players: dict[int, Player]
    ) -> None:
        def make_game_options(player: Player) -> GameLaunchOptions:
            return GameLaunchOptions(
                mapname=spec.map.folder_name,
                expected_players=len(spec.players),
                game_options=spec.game_options,
                team=game.get_player_option(player.id, "Team"),
                faction=game.get_player_option(player.id, "Faction"),
                map_position=game.get_player_option(player.id, "StartSpot"),
                map_pool_map_version_id=spec.map.map_pool_map_version_id
            )

        host = players[spec.host_id]
        guests = [
            player for player_id, player in players.items()
            if player_id != spec.host_id
        ]

        # Launch the host
        if host.lobby_connection is None:
            raise NotConnectedError([host])

        host.lobby_connection.write_launch_game(
            game,
            is_host=True,
            options=make_game_options(host)
        )

        try:
            await game.wait_hosted(60)
        except asyncio.TimeoutError:
            raise NotConnectedError([host])
        finally:
            # TODO: Once the client supports `match_cancelled`, don't
            # send `launch_game` to the client if the host timed out. Until
            # then, failing to send `launch_game` will cause the client to
            # think it is searching for ladder, even though the server has
            # already removed it from the queue.

            # Launch the guests
            not_connected_guests = [
                player for player in guests
                if player.lobby_connection is None
            ]
            if not_connected_guests:
                raise NotConnectedError(not_connected_guests)

            for guest in guests:
                assert guest.lobby_connection is not None

                guest.lobby_connection.write_launch_game(
                    game,
                    is_host=False,
                    options=make_game_options(guest)
                )
        try:
            await game.wait_launched(60 + 10 * len(guests))
        except asyncio.TimeoutError:
            connected_players = game.get_connected_players()
            raise NotConnectedError([
                player for player in guests
                if player not in connected_players
            ])

    def _make_failure_result(
        self,
        e: Exception,
        game: Optional[LadderGame]
    ) -> MatchLaunchResult:
        game_id = game.id if game else None

        if isinstance(e, NotConnectedError):
            self._logger.info("Match %s setup timed out", game)
            return MatchLaunchResult(
                game_id=game_id,
                failed_players=tuple(
                    PlayerLaunchFailure(
                        player.id, LaunchFailureReason.NOT_CONNECTED
                    )
                    for player in e.players
                )
            )
        if isinstance(e, GameClosedError):
            self._logger.info(
                "Match %s failed to start! Player %s closed their game "
                "instance",
                game, e.player
            )
            return MatchLaunchResult(
                game_id=game_id,
                failed_players=(
                    PlayerLaunchFailure(
                        e.player.id, LaunchFailureReason.ABORTED
                    ),
                )
            )

        # All timeout errors should be transformed into NotConnectedError
        assert not isinstance(e, asyncio.TimeoutError)

        self._logger.exception("Match %s failed to start", game, exc_info=e)
        return MatchLaunchResult(game_id=game_id, error=repr(e))

    def _release_unlaunched_players(self, players) -> None:
        """Make players that never got a game connection idle again."""
        # They would otherwise be stuck waiting for a match that is not going
        # to happen. Everyone else is released by their game connection.
        for player in players:
            if (
                player.state is PlayerState.STARTING_AUTOMATCH
                and player.game_connection is None
            ):
                player.state = PlayerState.IDLE
