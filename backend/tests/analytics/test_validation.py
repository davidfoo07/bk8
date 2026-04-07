"""Tests for the Data Validation Layer."""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.validation import DataValidator


class TestRangeValidation:
    """Tests for Tier 1: Range/Sanity Checks."""

    def setup_method(self):
        self.validator = DataValidator()

    def test_valid_ortg(self):
        result = self.validator.validate_range("ortg", 112.5)
        assert result.is_valid

    def test_invalid_ortg_too_high(self):
        result = self.validator.validate_range("ortg", 140.0)
        assert not result.is_valid
        assert result.severity == "WARNING"

    def test_invalid_ortg_too_low(self):
        result = self.validator.validate_range("ortg", 80.0)
        assert not result.is_valid

    def test_none_value(self):
        result = self.validator.validate_range("ortg", None)
        assert not result.is_valid

    def test_polymarket_price_range(self):
        assert self.validator.validate_range("polymarket_price", 0.50).is_valid
        assert not self.validator.validate_range("polymarket_price", 0.0).is_valid
        assert not self.validator.validate_range("polymarket_price", 1.0).is_valid

    def test_unknown_field(self):
        result = self.validator.validate_range("unknown_field", 100)
        assert result.is_valid  # No rule = passes

    def test_team_ratings_consistency(self):
        """NRtg should approximately equal ORtg - DRtg."""
        results = self.validator.validate_team_ratings(115.0, 108.0, 7.0)
        # 115 - 108 = 7.0, matches NRtg
        assert all(r.is_valid for r in results)

    def test_team_ratings_inconsistency(self):
        """NRtg not matching ORtg - DRtg should warn."""
        results = self.validator.validate_team_ratings(115.0, 108.0, 3.0)
        # 115 - 108 = 7.0, but NRtg is 3.0 → diff of 4.0 > 1.0
        warnings = [r for r in results if not r.is_valid]
        assert len(warnings) > 0


class TestCrossSourceValidation:
    """Tests for Tier 2: Cross-Source Verification."""

    def setup_method(self):
        self.validator = DataValidator()

    def test_sources_agree(self):
        result = self.validator.validate_cross_source(
            "ortg", 115.0, "nba_api", 115.5, "pbpstats"
        )
        assert result.is_valid

    def test_sources_disagree(self):
        result = self.validator.validate_cross_source(
            "ortg", 115.0, "nba_api", 120.0, "pbpstats"
        )
        assert not result.is_valid
        assert result.severity == "WARNING"


class TestStalenessDetection:
    """Tests for Tier 3: Staleness Detection."""

    def setup_method(self):
        self.validator = DataValidator()

    def test_fresh_data(self):
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = self.validator.check_staleness("polymarket_prices", recent)
        assert result.is_valid

    def test_stale_data(self):
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        result = self.validator.check_staleness("polymarket_prices", old)
        assert not result.is_valid

    def test_no_timestamp(self):
        result = self.validator.check_staleness("team_ratings", None)
        assert not result.is_valid


class TestAnomalyDetection:
    """Tests for Tier 4: Anomaly Detection."""

    def setup_method(self):
        self.validator = DataValidator()

    def test_normal_nrtg_change(self):
        result = self.validator.check_nrtg_anomaly("DET", 5.0, 2.0)
        assert result.is_valid  # Change of 3.0 < threshold of 8.0

    def test_anomalous_nrtg_change(self):
        result = self.validator.check_nrtg_anomaly("DET", 5.0, -5.0)
        assert not result.is_valid  # Change of 10.0 > threshold of 8.0

    def test_normal_price_movement(self):
        result = self.validator.check_price_movement("CLE ML", 0.50, 0.55)
        assert result.is_valid

    def test_major_price_movement(self):
        result = self.validator.check_price_movement("CLE ML", 0.50, 0.70)
        assert not result.is_valid  # Movement of 0.20 > threshold of 0.15
