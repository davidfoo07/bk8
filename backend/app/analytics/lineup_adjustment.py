"""
Lineup Adjustment Engine — the CORE feature.
Pluggable model interface with V1: Additive On/Off Splits.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from loguru import logger

from app.schemas.team import AdjustedRatings, PlayerAbsence


class LineupAdjustmentModel(ABC):
    """Abstract interface for lineup adjustment models."""

    @abstractmethod
    def calculate_adjusted_ratings(
        self,
        team_id: str,
        season_ortg: float,
        season_drtg: float,
        missing_players: list[PlayerAbsence],
        minutes_context: dict | None = None,
    ) -> AdjustedRatings:
        """Calculate lineup-adjusted ratings for a team."""
        ...


class OnOffSplitModel(LineupAdjustmentModel):
    """
    V1 Implementation: Additive On/Off Splits.

    For each missing player:
    1. Player impact = on_court_rating - off_court_rating
    2. Weighted impact = impact * minutes_share
    3. For 2+ missing: diminishing returns factor (0.85 per additional player)
    4. Apply summed deltas to team baseline

    Confidence based on on/off minutes sample size.
    """

    DIMINISHING_RETURNS_FACTOR = 0.85

    def calculate_adjusted_ratings(
        self,
        team_id: str,
        season_ortg: float,
        season_drtg: float,
        missing_players: list[PlayerAbsence],
        minutes_context: dict | None = None,
    ) -> AdjustedRatings:
        """Calculate adjusted ratings based on missing players' on/off splits."""
        season_nrtg = season_ortg - season_drtg

        if not missing_players:
            return AdjustedRatings(
                team=team_id,
                season_ortg=season_ortg,
                season_drtg=season_drtg,
                season_nrtg=season_nrtg,
                adjusted_ortg=season_ortg,
                adjusted_drtg=season_drtg,
                adjusted_nrtg=season_nrtg,
                ortg_delta=0.0,
                drtg_delta=0.0,
                nrtg_delta=0.0,
                missing_players=[],
                confidence="HIGH",
                data_source="pbpstats",
                last_updated=datetime.now(timezone.utc),
            )

        # Calculate individual impacts (already provided in PlayerAbsence)
        total_ortg_impact = 0.0
        total_drtg_impact = 0.0

        for i, player in enumerate(missing_players):
            # Apply diminishing returns for multiple missing players
            if i == 0:
                factor = 1.0
            else:
                factor = self.DIMINISHING_RETURNS_FACTOR ** i

            # Impact is weighted by minutes share and diminishing returns
            ortg_impact = player.ortg_impact * factor
            drtg_impact = player.drtg_impact * factor

            total_ortg_impact += ortg_impact
            total_drtg_impact += drtg_impact

            logger.debug(
                f"Player {player.name}: ORtg impact={player.ortg_impact:.1f} "
                f"(weighted={ortg_impact:.1f}), DRtg impact={player.drtg_impact:.1f} "
                f"(weighted={drtg_impact:.1f}), factor={factor:.2f}"
            )

        # Apply impacts to baseline
        # Negative ortg_impact means the team is WORSE without this player
        adjusted_ortg = season_ortg + total_ortg_impact
        adjusted_drtg = season_drtg + total_drtg_impact
        adjusted_nrtg = adjusted_ortg - adjusted_drtg

        ortg_delta = adjusted_ortg - season_ortg
        drtg_delta = adjusted_drtg - season_drtg
        nrtg_delta = adjusted_nrtg - season_nrtg

        # Determine confidence based on data quality
        confidence = self._calculate_confidence(missing_players, minutes_context)

        logger.info(
            f"{team_id} adjusted: ORtg {season_ortg:.1f} → {adjusted_ortg:.1f} "
            f"({ortg_delta:+.1f}), DRtg {season_drtg:.1f} → {adjusted_drtg:.1f} "
            f"({drtg_delta:+.1f}), NRtg {season_nrtg:.1f} → {adjusted_nrtg:.1f} "
            f"({nrtg_delta:+.1f}), confidence={confidence}"
        )

        return AdjustedRatings(
            team=team_id,
            season_ortg=season_ortg,
            season_drtg=season_drtg,
            season_nrtg=season_nrtg,
            adjusted_ortg=round(adjusted_ortg, 1),
            adjusted_drtg=round(adjusted_drtg, 1),
            adjusted_nrtg=round(adjusted_nrtg, 1),
            ortg_delta=round(ortg_delta, 1),
            drtg_delta=round(drtg_delta, 1),
            nrtg_delta=round(nrtg_delta, 1),
            missing_players=missing_players,
            confidence=confidence,
            data_source="pbpstats",
            last_updated=datetime.now(timezone.utc),
        )

    def _calculate_confidence(
        self,
        missing_players: list[PlayerAbsence],
        minutes_context: dict | None = None,
    ) -> str:
        """
        Confidence based on data quality:
        - HIGH: >200 on/off minutes sample for all missing players
        - MEDIUM: 100-200 minutes sample
        - LOW: <100 minutes sample or missing data
        """
        if not minutes_context:
            # Without minutes context, base on number of missing players
            if len(missing_players) <= 1:
                return "MEDIUM"
            elif len(missing_players) <= 3:
                return "MEDIUM"
            else:
                return "LOW"

        min_minutes = float("inf")
        for player in missing_players:
            player_mins = minutes_context.get(player.player_id, {})
            on_mins = player_mins.get("on_minutes", 0)
            off_mins = player_mins.get("off_minutes", 0)
            total = on_mins + off_mins
            min_minutes = min(min_minutes, total)

        if min_minutes == float("inf"):
            return "LOW"
        elif min_minutes >= 200:
            return "HIGH"
        elif min_minutes >= 100:
            return "MEDIUM"
        else:
            return "LOW"


def compute_player_impact(
    on_ortg: float,
    off_ortg: float,
    on_drtg: float,
    off_drtg: float,
    minutes_share: float,
) -> tuple[float, float, float]:
    """
    Compute a player's impact on team ratings based on on/off splits.

    Returns (ortg_impact, drtg_impact, nrtg_impact).
    Negative ortg_impact means team gets WORSE offensively without this player.
    Positive drtg_impact means team gets WORSE defensively without this player.
    """
    # Impact is the difference: what team loses when player is OUT
    # If on_court ORtg is higher, player helps offense → losing them hurts
    ortg_diff = on_ortg - off_ortg  # positive = player helps offense
    drtg_diff = on_drtg - off_drtg  # negative = player helps defense (lower is better)

    # Weight by minutes share
    ortg_impact = -(ortg_diff * minutes_share)  # negative = team gets worse
    drtg_impact = -(drtg_diff * minutes_share)  # positive = team gets worse (higher DRtg)

    nrtg_impact = ortg_impact - drtg_impact

    return (round(ortg_impact, 1), round(drtg_impact, 1), round(nrtg_impact, 1))
