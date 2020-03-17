from collections import Counter
from collections.abc import Mapping
from enum import Enum
from typing import NamedTuple

from server.decorators import with_logger


class GameOutcome(Enum):
    VICTORY = 'victory'
    DEFEAT = 'defeat'
    DRAW = 'draw'
    MUTUAL_DRAW = 'mutual_draw'
    UNKNOWN = 'unknown'
    CONFLICTING = 'conflicting'

    @classmethod
    def from_message(cls, msg: str):
        try:
            return cls(msg.lower())
        except ValueError:
            return cls.UNKNOWN


class GameResult(NamedTuple):
    """
    These are sent from each player's FA when they quit the game. 'Score'
    depends on the number of ACUs killed, whether the player died, maybe other
    factors.
    """
    reporter: int
    army: int
    outcome: GameOutcome
    score: int


@with_logger
class GameResults(Mapping):
    """
    Collects all results from a single game. Allows to determine results for an
    army and game as a whole. Supports a dict-like access to lists of results
    for each army, but don't modify these.
    """
    def __init__(self, game_id):
        Mapping.__init__(self)
        self._game_id = game_id    # Just for logging
        self._back = {}

    def __getitem__(self, key: int):
        return self._back[key]

    def __iter__(self):
        return iter(self._back)

    def __len__(self):
        return len(self._back)

    def add(self, result: GameResult):
        army_results = self._back.setdefault(result.army, [])
        army_results.append(result)

    def is_mutually_agreed_draw(self, player_armies):
        # Can't tell if we have no results
        if not self:
            return False
        # Everyone has to agree to a mutual draw
        for army in player_armies:
            if army not in self:
                continue
            if any(
                r.outcome is not GameOutcome.MUTUAL_DRAW for r in self[army]
            ):
                return False
        return True

    def outcome(self, army: int) -> GameOutcome:
        """
        Determines what the game outcome was for a given army. Returns the
        outcome all players agree on, excluding players that reported an
        unknown outcome. Reports unknown outcome if players disagree.
        """
        if army not in self:
            return GameOutcome.UNKNOWN

        outcomes = set(
            r.outcome for r in self[army]
            if r.outcome is not GameOutcome.UNKNOWN
        )

        if len(outcomes) == 1:
            return outcomes.pop()
        elif len(outcomes) > 1:
            self._logger.info(
                "Multiple outcomes for game %s army %s: %s", self._game_id,
                army, list(outcomes)
            )
            return GameOutcome.CONFLICTING

        return GameOutcome.UNKNOWN

    def score(self, army: int):
        """
        Pick and return most frequently reported score for an army. If multiple
        scores are most frequent, pick the largest one. Returns 0 if there are
        no results for a given army.
        """
        if army not in self:
            return 0

        scores = Counter(r.score for r in self[army])
        if len(scores) == 1:
            return scores.popitem()[0]

        self._logger.info(
            "Conflicting scores (%s) reported for game %s", scores,
            self._game_id
        )
        score, _ = max(scores.items(), key=lambda kv: kv[::-1])
        return score

    def victory_only_score(self, army: int):
        """
        Calculate our own score depending *only* on victory.
        """
        if army not in self:
            return 0

        if any(r.outcome is GameOutcome.VICTORY for r in self[army]):
            return 1
        else:
            return 0

    @classmethod
    async def from_db(cls, database, game_id):
        results = cls(game_id)
        async with database.acquire() as conn:
            rows = await conn.execute(
                "SELECT `place`, `score`, `result` "
                "FROM `game_player_stats` "
                "WHERE `gameId`=%s", (game_id, )
            )

            async for row in rows:
                startspot, score = row[0], row[1]
                # FIXME: Assertion about startspot == army
                # FIXME: Reporter not retained in database
                # TODO: I don't understand the comment above
                # there is no unique reporter for a score,
                # only a consolidated score is saved in the database
                # Is this asking us to save _all_ reports in the DB?
                outcome = GameOutcome[row[2]]
                result = GameResult(0, startspot, outcome, score)
                results.add(result)
        return results
