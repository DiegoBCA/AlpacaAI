"""
Tests for the Aggressiveness Engine.

These test the pure function with zero I/O — fast, deterministic, no mocks needed.
"""

import pytest

from app.aggressiveness import (
    AggressivenessProfile,
    get_aggressiveness_profile,
    CONSERVATIVE_MAX,
    MODERATE_MAX,
)


# ---------------------------------------------------------------------------
# Conservative zone (0-35)
# ---------------------------------------------------------------------------

class TestConservativeZone:
    """Tests for aggressiveness values 0-35."""

    def test_zero(self):
        p = get_aggressiveness_profile(0)
        assert p.zone == "conservative"
        assert p.zone_label == "Conservador"
        assert p.value == 0

    def test_mid_conservative(self):
        p = get_aggressiveness_profile(20)
        assert p.zone == "conservative"
        assert "ETF" in p.allowed_instruments
        assert "covered call" in p.allowed_instruments
        assert p.strategy_type == "covered_calls"

    def test_boundary_conservative(self):
        """35 is the last value in conservative zone."""
        p = get_aggressiveness_profile(35)
        assert p.zone == "conservative"
        assert p.stop_loss_pct == 0.02
        assert p.max_exposure_pct == 0.20
        assert p.max_concurrent_positions == 3

    def test_conservative_excludes_aggressive_instruments(self):
        p = get_aggressiveness_profile(10)
        assert "crypto" not in p.allowed_instruments
        assert "long call" not in p.allowed_instruments
        assert "naked put" not in p.allowed_instruments


# ---------------------------------------------------------------------------
# Moderate zone (36-65)
# ---------------------------------------------------------------------------

class TestModerateZone:
    """Tests for aggressiveness values 36-65."""

    def test_boundary_lower(self):
        """36 is the first value in moderate zone."""
        p = get_aggressiveness_profile(36)
        assert p.zone == "moderate"
        assert p.zone_label == "Moderado"

    def test_mid_moderate(self):
        p = get_aggressiveness_profile(50)
        assert p.zone == "moderate"
        assert "iron condor" in p.allowed_instruments
        assert "credit spread" in p.allowed_instruments
        assert p.strategy_type == "iron_condors_credit_spreads"

    def test_boundary_upper(self):
        """65 is the last value in moderate zone."""
        p = get_aggressiveness_profile(65)
        assert p.zone == "moderate"
        assert p.stop_loss_pct == 0.05
        assert p.max_exposure_pct == 0.40
        assert p.max_concurrent_positions == 5


# ---------------------------------------------------------------------------
# Aggressive zone (66-100)
# ---------------------------------------------------------------------------

class TestAggressiveZone:
    """Tests for aggressiveness values 66-100."""

    def test_boundary_lower(self):
        """66 is the first value in aggressive zone."""
        p = get_aggressiveness_profile(66)
        assert p.zone == "aggressive"
        assert p.zone_label == "Agresivo"

    def test_mid_aggressive(self):
        p = get_aggressiveness_profile(80)
        assert p.zone == "aggressive"
        assert "crypto" in p.allowed_instruments
        assert "long call" in p.allowed_instruments
        assert "long put" in p.allowed_instruments
        assert p.strategy_type == "directional_calls_puts"

    def test_max(self):
        p = get_aggressiveness_profile(100)
        assert p.zone == "aggressive"
        assert p.stop_loss_pct == 0.10
        assert p.max_exposure_pct == 0.60
        assert p.max_concurrent_positions == 8


# ---------------------------------------------------------------------------
# Edge cases and purity
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test boundary values and function purity."""

    def test_pure_function_same_input_same_output(self):
        """The function is pure: same input always gives same output."""
        a = get_aggressiveness_profile(50)
        b = get_aggressiveness_profile(50)
        assert a == b

    def test_frozen_dataclass(self):
        """Profile should be immutable."""
        p = get_aggressiveness_profile(50)
        with pytest.raises(AttributeError):
            p.value = 99  # type: ignore[misc]

    def test_negative_value_raises(self):
        with pytest.raises(ValueError, match="0-100"):
            get_aggressiveness_profile(-1)

    def test_over_100_raises(self):
        with pytest.raises(ValueError, match="0-100"):
            get_aggressiveness_profile(101)

    def test_float_raises_type_error(self):
        with pytest.raises(TypeError, match="int"):
            get_aggressiveness_profile(50.5)  # type: ignore[arg-type]

    def test_all_zones_covered(self):
        """Every value 0-100 maps to a valid zone."""
        for v in range(101):
            p = get_aggressiveness_profile(v)
            assert p.zone in ("conservative", "moderate", "aggressive")
            assert p.value == v

    def test_zone_boundaries_are_correct(self):
        """Verify the exact boundary transitions."""
        assert get_aggressiveness_profile(CONSERVATIVE_MAX).zone == "conservative"
        assert get_aggressiveness_profile(CONSERVATIVE_MAX + 1).zone == "moderate"
        assert get_aggressiveness_profile(MODERATE_MAX).zone == "moderate"
        assert get_aggressiveness_profile(MODERATE_MAX + 1).zone == "aggressive"
