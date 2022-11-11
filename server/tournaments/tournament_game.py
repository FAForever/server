from datetime import datetime
from enum import Enum

from server.players import Player
from server.timing import datetime_now


class TournamentGameState(Enum):
    SCHEDULED = 1
    CONFIRMATION_PENDING = 2
    STARTING = 3
    RUNNING = 4
    PLAYER_NOT_ONLINE = 5
    PLAYER_NOT_IDLE = 6
    PLAYER_NOT_CONFIRMING = 7
    PLAYER_NOT_STARTING = 8
    PLAYER_NOT_CONNECTING = 9

    def is_done(self):
        return self not in {
            TournamentGameState.SCHEDULED,
            TournamentGameState.CONFIRMATION_PENDING,
            TournamentGameState.STARTING
        }


class TournamentGameInfo:
    def __init__(
        self,
        request_id,
        game_name,
        participants,
        featured_mod,
        map_name,
        game_options,
    ):
        self.created_time = datetime_now()
        self.players = []
        self.players_ready_ids = set()
        self.state = TournamentGameState.SCHEDULED
        self.request_id = request_id
        self.name = game_name
        self.participants = participants
        self.featured_mod = featured_mod
        self.map_name = map_name
        self.game_options = game_options
        self.players_causing_cancel = set()
        self.response_time_seconds = 30
        self.participants_by_id = {participant.id: participant for participant in participants}

    def __contains__(self, player: Player) -> bool:
        return player in self.players

    def __iter__(self):
        return iter(self.players)

    def is_ready(self) -> bool:
        return set(player.id for player in self.players) == self.players_ready_ids

    def is_confirmation_overdue(self):
        time_passed = datetime.utcnow() - self.created_time
        return time_passed.seconds > self.response_time_seconds + 5

    def get_team_of_player(self, player) -> int:
        return self.get_participant_of_player(player)["team"]

    def get_slot_of_player(self, player) -> int:
        return self.get_participant_of_player(player)["slot"]

    def get_faction_of_player(self, player) -> int:
        return self.get_participant_of_player(player)["faction"]

    def get_participant_of_player(self, player):
        return self.participants_by_id[player.id]

    def get_error_code(self):
        return self.state.name
