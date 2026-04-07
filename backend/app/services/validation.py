"""Data Validation Layer — Tier 1-4 validation per PRD specification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.config import settings


# Tier 1: Range/Sanity Check Rules
VALIDATION_RULES: dict[str, dict[str, Any]] = {
    "ortg": {"min": 90.0, "max": 130.0, "description": "Offensive Rating"},
    "drtg": {"min": 90.0, "max": 130.0, "description": "Defensive Rating"},
    "nrtg": {"min": -25.0, "max": 25.0, "description": "Net Rating"},
    "pace": {"min": 90.0, "max": 110.0, "description": "Pace Factor"},
    "player_minutes": {"min": 0.0, "max": 48.0, "description": "Minutes Per Game"},
    "team_roster_size": {"min": 12, "max": 17, "description": "Active Roster Size"},
    "game_count": {"min": 1, "max": 82, "description": "Games Played"},
    "win_probability": {"min": 0.0, "max": 1.0, "description": "Win Probability"},
    "polymarket_price": {"min": 0.01, "max": 0.99, "description": "Market Price"},
    "minutes_share": {"min": 0.0, "max": 1.0, "description": "Minutes Share"},
}

# Tier 2: Cross-Source Tolerances
CROSS_SOURCE_TOLERANCE: dict[str, float] = {
    "ortg": 2.0,
    "drtg": 2.0,
    "nrtg": 3.0,
}

# Tier 3: Staleness Thresholds
STALENESS_THRESHOLDS: dict[str, timedelta] = {
    "team_ratings": timedelta(hours=24),
    "injury_reports": timedelta(hours=2),
    "polymarket_prices": timedelta(minutes=10),
}

# Tier 4: Anomaly Thresholds
ANOMALY_THRESHOLDS: dict[str, float] = {
    "nrtg_change": 8.0,  # Points from baseline
    "price_movement": 0.15,  # 15 cents in an hour
}


class ValidationResult:
    """Result of a validation check."""

    def __init__(
        self,
        is_valid: bool,
        check_type: str,
        severity: str,
        field: str,
        message: str,
        actual_value: Any = None,
        expected_range: str = "",
    ) -> None:
        self.is_valid = is_valid
        self.check_type = check_type
        self.severity = severity  # INFO, WARNING, ERROR
        self.field = field
        self.message = message
        self.actual_value = actual_value
        self.expected_range = expected_range

    def __repr__(self) -> str:
        return f"ValidationResult({self.severity}: {self.message})"


class DataValidator:
    """Comprehensive data validation engine implementing Tiers 1-4."""

    def __init__(self) -> None:
        self.validation_log: list[ValidationResult] = []

    def clear_log(self) -> None:
        """Clear the validation log."""
        self.validation_log = []

    # ─── Tier 1: Range/Sanity Checks ──────────────────────────────────

    def validate_range(
        self,
        field: str,
        value: float | int | None,
        source: str = "unknown",
    ) -> ValidationResult:
        """
        Validate a value falls within its expected range.
        Returns ValidationResult; logs WARNING if out of range.
        """
        if value is None:
            result = ValidationResult(
                is_valid=False,
                check_type="RANGE",
                severity="WARNING",
                field=field,
                message=f"{field} is None from {source}",
                actual_value=None,
                expected_range="not None",
            )
            self.validation_log.append(result)
            return result

        rule = VALIDATION_RULES.get(field)
        if rule is None:
            return ValidationResult(
                is_valid=True,
                check_type="RANGE",
                severity="INFO",
                field=field,
                message=f"No validation rule for {field}",
                actual_value=value,
            )

        min_val = rule["min"]
        max_val = rule["max"]
        is_valid = min_val <= float(value) <= max_val

        if not is_valid:
            result = ValidationResult(
                is_valid=False,
                check_type="RANGE",
                severity="WARNING",
                field=field,
                message=f"{rule['description']} value {value} out of range [{min_val}, {max_val}] from {source}",
                actual_value=value,
                expected_range=f"[{min_val}, {max_val}]",
            )
            logger.warning(result.message)
            self.validation_log.append(result)
            return result

        return ValidationResult(
            is_valid=True,
            check_type="RANGE",
            severity="INFO",
            field=field,
            message=f"{field} = {value} is valid",
            actual_value=value,
            expected_range=f"[{min_val}, {max_val}]",
        )

    def validate_team_ratings(
        self,
        ortg: float | None,
        drtg: float | None,
        nrtg: float | None,
        source: str = "unknown",
    ) -> list[ValidationResult]:
        """Validate a complete set of team ratings."""
        results = [
            self.validate_range("ortg", ortg, source),
            self.validate_range("drtg", drtg, source),
            self.validate_range("nrtg", nrtg, source),
        ]
        
        # Cross-check: NRtg should approximately equal ORtg - DRtg
        if ortg is not None and drtg is not None and nrtg is not None:
            expected_nrtg = ortg - drtg
            diff = abs(nrtg - expected_nrtg)
            if diff > 1.0:
                result = ValidationResult(
                    is_valid=False,
                    check_type="RANGE",
                    severity="WARNING",
                    field="nrtg_consistency",
                    message=f"NRtg ({nrtg}) != ORtg ({ortg}) - DRtg ({drtg}) = {expected_nrtg:.1f}, diff={diff:.1f}",
                    actual_value=nrtg,
                    expected_range=f"~{expected_nrtg:.1f}",
                )
                self.validation_log.append(result)
                results.append(result)
        
        return results

    # ─── Tier 2: Cross-Source Verification ─────────────────────────────

    def validate_cross_source(
        self,
        field: str,
        value_a: float,
        source_a: str,
        value_b: float,
        source_b: str,
    ) -> ValidationResult:
        """
        Compare values from two different sources.
        Flag if they disagree beyond tolerance.
        """
        tolerance = CROSS_SOURCE_TOLERANCE.get(field, 2.0)
        diff = abs(value_a - value_b)
        is_valid = diff <= tolerance

        if not is_valid:
            result = ValidationResult(
                is_valid=False,
                check_type="CROSS_SOURCE",
                severity="WARNING",
                field=field,
                message=f"{field} disagrees: {source_a}={value_a} vs {source_b}={value_b} (diff={diff:.1f}, tolerance={tolerance})",
                actual_value=f"{value_a} vs {value_b}",
                expected_range=f"within {tolerance}",
            )
            logger.warning(result.message)
            self.validation_log.append(result)
            return result

        return ValidationResult(
            is_valid=True,
            check_type="CROSS_SOURCE",
            severity="INFO",
            field=field,
            message=f"{field} sources agree: {source_a}={value_a}, {source_b}={value_b}",
            actual_value=f"{value_a} vs {value_b}",
            expected_range=f"within {tolerance}",
        )

    # ─── Tier 3: Staleness Detection ──────────────────────────────────

    def check_staleness(
        self,
        data_type: str,
        last_updated: datetime | None,
    ) -> ValidationResult:
        """Check if data is stale based on thresholds."""
        if last_updated is None:
            result = ValidationResult(
                is_valid=False,
                check_type="STALENESS",
                severity="WARNING",
                field=data_type,
                message=f"{data_type} has no timestamp — cannot verify freshness",
            )
            self.validation_log.append(result)
            return result

        threshold = STALENESS_THRESHOLDS.get(data_type, timedelta(hours=24))
        now = datetime.now(timezone.utc)
        
        # Make last_updated timezone-aware if it isn't
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        
        age = now - last_updated
        is_fresh = age <= threshold

        freshness = "FRESH" if is_fresh else "STALE"

        if not is_fresh:
            result = ValidationResult(
                is_valid=False,
                check_type="STALENESS",
                severity="WARNING",
                field=data_type,
                message=f"{data_type} is STALE (age: {age}, threshold: {threshold})",
                actual_value=str(age),
                expected_range=f"<= {threshold}",
            )
            logger.warning(result.message)
            self.validation_log.append(result)
            return result

        return ValidationResult(
            is_valid=True,
            check_type="STALENESS",
            severity="INFO",
            field=data_type,
            message=f"{data_type} is {freshness} (age: {age})",
            actual_value=str(age),
            expected_range=f"<= {threshold}",
        )

    # ─── Tier 4: Anomaly Detection ────────────────────────────────────

    def check_nrtg_anomaly(
        self,
        team: str,
        baseline_nrtg: float,
        adjusted_nrtg: float,
    ) -> ValidationResult:
        """Flag unusual NRtg changes."""
        delta = abs(adjusted_nrtg - baseline_nrtg)
        threshold = ANOMALY_THRESHOLDS["nrtg_change"]
        is_normal = delta <= threshold

        if not is_normal:
            result = ValidationResult(
                is_valid=False,
                check_type="ANOMALY",
                severity="WARNING",
                field="nrtg_change",
                message=f"{team} NRtg changed by {delta:.1f} points (baseline: {baseline_nrtg}, adjusted: {adjusted_nrtg}). Verify injuries.",
                actual_value=delta,
                expected_range=f"<= {threshold}",
            )
            logger.warning(result.message)
            self.validation_log.append(result)
            return result

        return ValidationResult(
            is_valid=True,
            check_type="ANOMALY",
            severity="INFO",
            field="nrtg_change",
            message=f"{team} NRtg change ({delta:.1f}) is within normal range",
            actual_value=delta,
            expected_range=f"<= {threshold}",
        )

    def check_price_movement(
        self,
        market: str,
        old_price: float,
        new_price: float,
    ) -> ValidationResult:
        """Flag major Polymarket price movements."""
        movement = abs(new_price - old_price)
        threshold = ANOMALY_THRESHOLDS["price_movement"]
        is_normal = movement <= threshold

        if not is_normal:
            direction = "up" if new_price > old_price else "down"
            result = ValidationResult(
                is_valid=False,
                check_type="ANOMALY",
                severity="WARNING",
                field="price_movement",
                message=f"{market} price moved {direction} by {movement:.2f} (${old_price:.2f} → ${new_price:.2f}). Major line movement.",
                actual_value=movement,
                expected_range=f"<= {threshold}",
            )
            logger.warning(result.message)
            self.validation_log.append(result)
            return result

        return ValidationResult(
            is_valid=True,
            check_type="ANOMALY",
            severity="INFO",
            field="price_movement",
            message=f"{market} price movement ({movement:.2f}) is normal",
            actual_value=movement,
            expected_range=f"<= {threshold}",
        )

    def get_warnings(self) -> list[ValidationResult]:
        """Get all WARNING and ERROR level results."""
        return [r for r in self.validation_log if r.severity in ("WARNING", "ERROR")]

    def get_freshness_status(self, data_type: str, last_updated: datetime | None) -> str:
        """Get a simple freshness string: FRESH, STALE, or MISSING."""
        if last_updated is None:
            return "MISSING"
        result = self.check_staleness(data_type, last_updated)
        return "FRESH" if result.is_valid else "STALE"


# Singleton instance for app-wide use
validator = DataValidator()
