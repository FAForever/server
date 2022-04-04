import time
from typing import Any, Callable, Optional, Sequence

from server.games.typedefs import FA, GameState, ValidityState, Victory

ValidationRule = Callable[["Game"], Optional[ValidityState]]


class Validator:
    def __init__(self, rules: Sequence[ValidationRule]):
        self.rules = rules

    def get_one(self, game: "Game") -> Optional[ValidityState]:
        for rule in self.rules:
            validity = rule(game)
            if validity is not None:
                return validity

    def get_all(self, game: "Game") -> list[ValidityState]:
        return [
            validity
            for rule in self.rules
            if (validity := rule(game)) is not None
        ]


class GameOptionRule:
    def __init__(self, key: str, value: Any, validity: ValidityState):
        self.key = key
        self.value = value
        self.validity = validity

    def __call__(self, game: "Game") -> Optional[ValidityState]:
        if game.game_options[self.key] != self.value:
            return self.validity


class PropertyRule:
    def __init__(self, name: str, value: Any, validity: ValidityState):
        self.name = name
        self.value = value
        self.validity = validity

    def __call__(self, game: "Game") -> Optional["ValidityState"]:
        if getattr(game, self.name) != self.value:
            return self.validity


def not_desynced_rule(game: "Game") -> Optional[ValidityState]:
    if game.desyncs > 20:
        return ValidityState.TOO_MANY_DESYNCS


def has_results_rule(game: "Game") -> Optional[ValidityState]:
    if game.state is GameState.ENDED and not game._results:
        return ValidityState.UNKNOWN_RESULT


def ranked_mods_rule(game: "Game") -> Optional[ValidityState]:
    for mod_id in game.mods.keys():
        if mod_id not in game.game_service.ranked_mods:
            return ValidityState.BAD_MOD


def ranked_map_rule(game: "Game") -> Optional[ValidityState]:
    if game.map_id is not None and not game.map_ranked:
        return ValidityState.BAD_MAP
    if game.map_id is None and not game.is_map_generated and not game.is_coop:
        return ValidityState.BAD_MAP


def even_teams_rule(game: "Game") -> Optional[ValidityState]:
    if None in game.teams or not game.is_even:
        return ValidityState.UNEVEN_TEAMS_NOT_RANKED


def multi_player_rule(game: "Game") -> Optional[ValidityState]:
    if len(game.players) < 2:
        return ValidityState.SINGLE_PLAYER


# Rules that apply for all games
COMMON_RULES = (
    not_desynced_rule,
    ranked_mods_rule,
    ranked_map_rule,
    PropertyRule("has_ai", False, ValidityState.HAS_AI_PLAYERS),
    PropertyRule("is_multi_team", False, ValidityState.MULTI_TEAM),
    PropertyRule("is_ffa", False, ValidityState.FFA_NOT_RANKED),
    GameOptionRule("AIReplacement", FA.DISABLED, ValidityState.HAS_AI_PLAYERS),
    GameOptionRule("FogOfWar", "explored", ValidityState.NO_FOG_OF_WAR),
    GameOptionRule("CheatsEnabled", FA.DISABLED, ValidityState.CHEATS_ENABLED),
    GameOptionRule("PrebuiltUnits", FA.DISABLED, ValidityState.PREBUILT_ENABLED),
    GameOptionRule("NoRushOption", FA.DISABLED, ValidityState.NORUSH_ENABLED),
    GameOptionRule("RestrictedCategories", 0, ValidityState.BAD_UNIT_RESTRICTIONS),
    GameOptionRule("TeamLock", "locked", ValidityState.UNLOCKED_TEAMS),
    GameOptionRule("Unranked", FA.DISABLED, ValidityState.HOST_SET_UNRANKED)
)
# Rules that apply for everything but coop
NON_COOP_RULES = (
    has_results_rule,
    even_teams_rule,
    multi_player_rule,
    GameOptionRule("Victory", Victory.DEMORALIZATION, ValidityState.WRONG_VICTORY_CONDITION)
)
