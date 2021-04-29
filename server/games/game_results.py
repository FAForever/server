import contextlib
from collections import Counter, defaultdict
from collections.abc import Mapping
from enum import Enum
from typing import Dict, FrozenSet, Iterator, List, NamedTuple, Optional, Set

from server.decorators import with_logger


class ArmyOutcome(Enum):
    """
    The resolved outcome for an army. Each army has only one of these.
    """
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    DRAW = "DRAW"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class ArmyReportedOutcome(Enum):
    """
    A reported outcome for an army. Each army may have several of these.
    """
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    DRAW = "DRAW"
    # This doesn't seem to be reported by the game anymore
    MUTUAL_DRAW = "MUTUAL_DRAW"

    def to_resolved(self) -> ArmyOutcome:
        """
        Convert this result to the resolved version. For when all reported
        results agree.
        """
        value = self.value
        if value == "MUTUAL_DRAW":
            value = "DRAW"
        return ArmyOutcome(value)


class ArmyResult(NamedTuple):
    """
    Broadcast in the end of game rabbitmq message.
    """
    player_id: int
    army: Optional[int]
    army_result: ArmyOutcome
    metadata: List[str]


class GameOutcome(Enum):
    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"
    DRAW = "DRAW"
    UNKNOWN = "UNKNOWN"


class GameResultReport(NamedTuple):
    """
    These are sent from each player's FA when they quit the game. 'Score'
    depends on the number of ACUs killed, whether the player died, maybe other
    factors.
    """

    reporter: int
    army: int
    outcome: ArmyReportedOutcome
    score: int
    metadata: FrozenSet[str] = []


@with_logger
class GameResultReports(Mapping):
    """
    Collects all results from a single game. Allows to determine results for an
    army and game as a whole. Supports a dict-like access to lists of results
    for each army, but don't modify these.
    """

    def __init__(self, game_id: int):
        Mapping.__init__(self)
        self._game_id = game_id  # Just for logging
        self._back: Dict[int, List[GameResultReport]] = {}
        # Outcome caching
        self._outcomes: Dict[int, ArmyOutcome] = {}
        self._dirty_armies: Set[int] = set()

    def __getitem__(self, key: int) -> List[GameResultReport]:
        return self._back[key]

    def __iter__(self) -> Iterator[int]:
        return iter(self._back)

    def __len__(self) -> int:
        return len(self._back)

    def add(self, result: GameResultReport) -> None:
        army_results = self._back.setdefault(result.army, [])
        army_results.append(result)
        self._dirty_armies.add(result.army)

    def is_mutually_agreed_draw(self, player_armies) -> bool:
        # Can't tell if we have no results
        if not self:
            return False
        # Everyone has to agree to a mutual draw
        for army in player_armies:
            if army not in self:
                continue
            if any(r.outcome is not ArmyReportedOutcome.MUTUAL_DRAW for r in self[army]):
                return False
        return True

    def outcome(self, army: int) -> ArmyOutcome:
        """
        Determines what the outcome was for a given army.
        Returns the unique reported outcome if all players agree,
        or the majority outcome if only a few reports disagree.
        Otherwise returns CONFLICTING if there is too much disagreement
        or UNKNOWN if no reports were filed.
        """
        if army not in self._outcomes or army in self._dirty_armies:
            self._outcomes[army] = self._compute_outcome(army)
            self._dirty_armies.discard(army)

        return self._outcomes[army]

    def _compute_outcome(self, army: int) -> ArmyOutcome:
        if army not in self:
            return ArmyOutcome.UNKNOWN

        voters = defaultdict(set)
        for report in self[army]:
            voters[report.outcome].add(report.reporter)

        if len(voters) == 0:
            return ArmyOutcome.UNKNOWN

        if len(voters) == 1:
            unique_outcome = voters.popitem()[0]
            return unique_outcome.to_resolved()

        sorted_outcomes = sorted(
            voters.keys(),
            reverse=True,
            key=lambda outcome: (len(voters[outcome]), outcome.value),
        )

        top_votes = len(voters[sorted_outcomes[0]])
        runner_up_votes = len(voters[sorted_outcomes[1]])
        if top_votes > 1 >= runner_up_votes or top_votes >= runner_up_votes + 3:
            decision = sorted_outcomes[0].to_resolved()
        else:
            decision = ArmyOutcome.CONFLICTING

        self._logger.info(
            "Multiple outcomes for game %s army %s resolved to %s. Reports are: %s",
            self._game_id, army, decision, voters,
        )
        return decision

    def metadata(self, army: int) -> List[str]:
        """
        If any users have sent metadata tags in their messages about this army
        this function will compare those tags across all messages trying to find
        common ones to return.
        """
        if army not in self:
            return []

        all_metadata = [report.metadata for report in self[army] if report.metadata]
        metadata_count = Counter(all_metadata).most_common()
        if not len(metadata_count):
            return []
        elif len(metadata_count) == 1:
            # Everyone agrees!
            return sorted(list(metadata_count[0][0]))
        else:
            most_common, next_most_common, *_ = metadata_count
            if most_common[1] > next_most_common[1]:
                resolved_to = sorted(list(most_common[0]))
                self._logger.info(
                    "Conflicting metadata for game %s army %s resolved to %s. Reports are: %s",
                    self._game_id, army, resolved_to, all_metadata,
                )
                return resolved_to
            else:
                # We have a tie
                self._logger.info(
                    "Conflicting metadata for game %s army %s, unable to resolve. Reports are: %s",
                    self._game_id, army, all_metadata,
                )
                return []

    def score(self, army: int) -> int:
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
            "Conflicting scores (%s) reported for game %s", scores, self._game_id
        )
        score, _ = max(scores.items(), key=lambda kv: kv[::-1])
        return score

    def victory_only_score(self, army: int) -> int:
        """
        Calculate our own score depending *only* on victory.
        """
        if army not in self:
            return 0

        if self.outcome(army) is ArmyOutcome.VICTORY:
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
                "WHERE `gameId`=%s",
                (game_id,),
            )

            async for row in rows:
                startspot, score = row[0], row[1]
                # FIXME: Assertion about startspot == army
                with contextlib.suppress(ValueError):
                    outcome = ArmyReportedOutcome(row[2])
                    result = GameResultReport(0, startspot, outcome, score)
                    results.add(result)
        return results


class GameResolutionError(Exception):
    pass


def resolve_game(team_outcomes: List[Set[ArmyOutcome]]) -> List[GameOutcome]:
    """
    Takes a list of length two containing sets of ArmyOutcome
    for individual players on a team
    and converts a list of two GameOutcomes,
    either VICTORY and DEFEAT or DRAW and DRAW.

    # Params
    - `team_outcomes`: list of `GameOutcomes`

    # Errors
    Throws `GameResolutionError` if outcomes are inconsistent or ambiguous.

    # Returns
    A list of ranks as to be used with trueskill
    """
    if len(team_outcomes) != 2:
        raise GameResolutionError(
            "Will not resolve game with other than two parties."
        )

    victory0 = ArmyOutcome.VICTORY in team_outcomes[0]
    victory1 = ArmyOutcome.VICTORY in team_outcomes[1]
    both_claim_victory = victory0 and victory1
    someone_claims_victory = victory0 or victory1
    if both_claim_victory:
        raise GameResolutionError(
            "Cannot resolve game in which both teams claimed victory. "
            f" Team outcomes: {team_outcomes}"
        )
    elif someone_claims_victory:
        return [
            GameOutcome.VICTORY
            if ArmyOutcome.VICTORY in outcomes
            else GameOutcome.DEFEAT
            for outcomes in team_outcomes
        ]

    # Now know that no-one has GameOutcome.VICTORY
    draw0 = ArmyOutcome.DRAW in team_outcomes[0]
    draw1 = ArmyOutcome.DRAW in team_outcomes[1]
    both_claim_draw = draw0 and draw1
    someone_claims_draw = draw0 or draw1
    if both_claim_draw:
        return [GameOutcome.DRAW, GameOutcome.DRAW]
    elif someone_claims_draw:
        raise GameResolutionError(
            "Cannot resolve game with unilateral draw. "
            f"Team outcomes: {team_outcomes}"
        )

    # Now know that the only results are DEFEAT or UNKNOWN/CONFLICTING
    # Unrank if there are any players with unknown result
    all_outcomes = team_outcomes[0] | team_outcomes[1]
    if (
        ArmyOutcome.UNKNOWN in all_outcomes
        or ArmyOutcome.CONFLICTING in all_outcomes
    ):
        raise GameResolutionError(
            "Cannot resolve game with ambiguous outcome. "
            f" Team outcomes: {team_outcomes}"
        )

    # Otherwise everyone is DEFEAT, we return a draw
    return [GameOutcome.DRAW, GameOutcome.DRAW]
