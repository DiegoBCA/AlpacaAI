"""
SILVERCAWN — Risk Gates.

Programmatic safety checks executed BEFORE any order is sent via MCP.
These are the hard limits that the LLM cannot override.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.aggressiveness import AggressivenessProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskCheckResult:
    """Result of a risk gate check."""

    allowed: bool
    gate_name: str | None = None  # Which gate blocked, if any
    reason: str | None = None  # Human-readable explanation


def check_paper_trading_guard(base_url: str | None = None) -> RiskCheckResult:
    """
    Hardcoded guard: never allow live trading.

    This is a belt-and-suspenders check on top of the config guard.
    """
    if base_url and "live" in base_url.lower() and "paper" not in base_url.lower():
        return RiskCheckResult(
            allowed=False,
            gate_name="paper_trading_guard",
            reason="BLOCKED: Attempted connection to live trading endpoint. "
            "SILVERCAWN only supports paper trading.",
        )
    return RiskCheckResult(allowed=True)


def check_position_limit(
    profile: AggressivenessProfile,
    current_position_count: int,
) -> RiskCheckResult:
    """Check if opening a new position would exceed the maximum allowed."""
    if current_position_count >= profile.max_concurrent_positions:
        return RiskCheckResult(
            allowed=False,
            gate_name="position_limit",
            reason=(
                f"Position limit reached: {current_position_count}/{profile.max_concurrent_positions} "
                f"positions for {profile.zone} zone."
            ),
        )
    return RiskCheckResult(allowed=True)


def check_exposure_limit(
    profile: AggressivenessProfile,
    proposed_order_value: float,
    current_exposure: float,
    account_equity: float,
) -> RiskCheckResult:
    """Check if the new order would push total exposure beyond the allowed percentage."""
    if account_equity <= 0:
        return RiskCheckResult(
            allowed=False,
            gate_name="exposure_limit",
            reason="Account equity is zero or negative — cannot evaluate exposure.",
        )

    new_total_exposure = current_exposure + proposed_order_value
    max_allowed = profile.max_exposure_pct * account_equity

    if new_total_exposure > max_allowed:
        return RiskCheckResult(
            allowed=False,
            gate_name="exposure_limit",
            reason=(
                f"Exposure limit exceeded: ${new_total_exposure:,.2f} would exceed "
                f"max ${max_allowed:,.2f} ({profile.max_exposure_pct:.0%} of ${account_equity:,.2f}) "
                f"for {profile.zone} zone."
            ),
        )
    return RiskCheckResult(allowed=True)


def check_instrument_allowed(
    profile: AggressivenessProfile,
    instrument_type: str,
) -> RiskCheckResult:
    """Check if the instrument type is permitted in the current aggressiveness zone."""
    # Normalize for comparison
    normalized = instrument_type.lower().strip()
    allowed_normalized = [i.lower() for i in profile.allowed_instruments]

    if normalized not in allowed_normalized:
        return RiskCheckResult(
            allowed=False,
            gate_name="instrument_check",
            reason=(
                f"Instrument '{instrument_type}' is not allowed in {profile.zone} zone. "
                f"Allowed: {', '.join(profile.allowed_instruments)}."
            ),
        )
    return RiskCheckResult(allowed=True)


async def run_all_risk_checks(
    profile: AggressivenessProfile,
    proposed_order: dict,
    current_positions: list,
    account_equity: float,
    current_exposure: float | None = None,
) -> RiskCheckResult:
    """
    Run ALL risk gates in sequence. Returns the first failure, or success.

    Args:
        profile: Current aggressiveness profile.
        proposed_order: Dict with at least 'instrument_type' and 'estimated_value'.
        current_positions: List of current open positions.
        account_equity: Current account equity value.
        current_exposure: Total value of current exposure (if None, estimated from positions).
    """
    # 1. Paper trading guard
    result = check_paper_trading_guard()
    if not result.allowed:
        logger.warning("RISK GATE BLOCKED: %s", result.reason)
        return result

    # 2. Position limit
    result = check_position_limit(profile, len(current_positions))
    if not result.allowed:
        logger.warning("RISK GATE BLOCKED: %s", result.reason)
        return result

    # 3. Exposure limit
    if current_exposure is None:
        # Estimate exposure from positions (sum of market values)
        current_exposure = sum(
            abs(float(p.get("market_value", 0))) for p in current_positions
        )

    order_value = float(proposed_order.get("estimated_value", 0))
    result = check_exposure_limit(profile, order_value, current_exposure, account_equity)
    if not result.allowed:
        logger.warning("RISK GATE BLOCKED: %s", result.reason)
        return result

    # 4. Instrument type check
    instrument_type = proposed_order.get("instrument_type", "unknown")
    result = check_instrument_allowed(profile, instrument_type)
    if not result.allowed:
        logger.warning("RISK GATE BLOCKED: %s", result.reason)
        return result

    logger.info("All risk gates passed for order: %s", proposed_order)
    return RiskCheckResult(allowed=True)
