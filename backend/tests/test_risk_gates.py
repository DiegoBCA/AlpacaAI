"""
Tests for the Risk Gates.

Tests each gate individually and the composite check.
"""

import pytest

from app.aggressiveness import get_aggressiveness_profile
from app.risk_gates import (
    check_exposure_limit,
    check_instrument_allowed,
    check_paper_trading_guard,
    check_position_limit,
    run_all_risk_checks,
)


# ---------------------------------------------------------------------------
# Paper Trading Guard
# ---------------------------------------------------------------------------

class TestPaperTradingGuard:
    def test_allows_paper(self):
        result = check_paper_trading_guard("https://paper-api.alpaca.markets")
        assert result.allowed is True

    def test_blocks_live(self):
        result = check_paper_trading_guard("https://api.alpaca.markets/live")
        assert result.allowed is False
        assert result.gate_name == "paper_trading_guard"

    def test_allows_none(self):
        result = check_paper_trading_guard(None)
        assert result.allowed is True

    def test_allows_empty(self):
        result = check_paper_trading_guard("")
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Position Limit
# ---------------------------------------------------------------------------

class TestPositionLimit:
    def test_allows_under_limit(self):
        profile = get_aggressiveness_profile(20)  # conservative, max 3
        result = check_position_limit(profile, 2)
        assert result.allowed is True

    def test_blocks_at_limit(self):
        profile = get_aggressiveness_profile(20)  # conservative, max 3
        result = check_position_limit(profile, 3)
        assert result.allowed is False
        assert result.gate_name == "position_limit"

    def test_blocks_over_limit(self):
        profile = get_aggressiveness_profile(50)  # moderate, max 5
        result = check_position_limit(profile, 6)
        assert result.allowed is False

    def test_allows_zero_positions(self):
        profile = get_aggressiveness_profile(80)  # aggressive, max 8
        result = check_position_limit(profile, 0)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Exposure Limit
# ---------------------------------------------------------------------------

class TestExposureLimit:
    def test_allows_under_limit(self):
        profile = get_aggressiveness_profile(20)  # conservative, 20% max
        # 100k equity, 10k existing + 5k new = 15k < 20k (20%)
        result = check_exposure_limit(profile, 5000, 10000, 100000)
        assert result.allowed is True

    def test_blocks_over_limit(self):
        profile = get_aggressiveness_profile(20)  # conservative, 20% max
        # 100k equity, 15k existing + 10k new = 25k > 20k
        result = check_exposure_limit(profile, 10000, 15000, 100000)
        assert result.allowed is False
        assert result.gate_name == "exposure_limit"

    def test_blocks_zero_equity(self):
        profile = get_aggressiveness_profile(50)
        result = check_exposure_limit(profile, 1000, 0, 0)
        assert result.allowed is False

    def test_exact_limit_allowed(self):
        profile = get_aggressiveness_profile(20)  # 20% = 20k on 100k
        result = check_exposure_limit(profile, 10000, 10000, 100000)
        assert result.allowed is True  # exactly at limit, not over


# ---------------------------------------------------------------------------
# Instrument Check
# ---------------------------------------------------------------------------

class TestInstrumentCheck:
    def test_etf_allowed_conservative(self):
        profile = get_aggressiveness_profile(20)
        result = check_instrument_allowed(profile, "ETF")
        assert result.allowed is True

    def test_crypto_blocked_conservative(self):
        profile = get_aggressiveness_profile(20)
        result = check_instrument_allowed(profile, "crypto")
        assert result.allowed is False
        assert result.gate_name == "instrument_check"

    def test_crypto_allowed_aggressive(self):
        profile = get_aggressiveness_profile(80)
        result = check_instrument_allowed(profile, "crypto")
        assert result.allowed is True

    def test_case_insensitive(self):
        profile = get_aggressiveness_profile(20)
        result = check_instrument_allowed(profile, "etf")
        assert result.allowed is True

    def test_iron_condor_moderate(self):
        profile = get_aggressiveness_profile(50)
        result = check_instrument_allowed(profile, "iron condor")
        assert result.allowed is True

    def test_iron_condor_blocked_conservative(self):
        profile = get_aggressiveness_profile(20)
        result = check_instrument_allowed(profile, "iron condor")
        assert result.allowed is False


# ---------------------------------------------------------------------------
# Composite check: run_all_risk_checks
# ---------------------------------------------------------------------------

class TestRunAllRiskChecks:
    @pytest.mark.asyncio
    async def test_all_pass(self):
        profile = get_aggressiveness_profile(20)  # conservative
        result = await run_all_risk_checks(
            profile=profile,
            proposed_order={"instrument_type": "covered call", "estimated_value": 5000},
            current_positions=[],
            account_equity=100000,
            current_exposure=0,
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_fails_on_position_limit(self):
        profile = get_aggressiveness_profile(20)  # max 3 positions
        positions = [{"id": i} for i in range(3)]  # Already at limit
        result = await run_all_risk_checks(
            profile=profile,
            proposed_order={"instrument_type": "covered call", "estimated_value": 5000},
            current_positions=positions,
            account_equity=100000,
            current_exposure=0,
        )
        assert result.allowed is False
        assert result.gate_name == "position_limit"

    @pytest.mark.asyncio
    async def test_fails_on_instrument(self):
        profile = get_aggressiveness_profile(20)  # conservative
        result = await run_all_risk_checks(
            profile=profile,
            proposed_order={"instrument_type": "crypto", "estimated_value": 1000},
            current_positions=[],
            account_equity=100000,
            current_exposure=0,
        )
        assert result.allowed is False
        assert result.gate_name == "instrument_check"
