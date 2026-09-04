"""
SIGMA IA — Aggressiveness Engine.

Pure function with zero I/O dependencies. Maps a 0-100 integer to a complete
trading profile including zone, instruments, strategy, and risk limits.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AggressivenessProfile:
    """Immutable trading profile derived from an aggressiveness value."""

    value: int
    zone: str  # "conservative" | "moderate" | "aggressive"
    zone_label: str  # Human-readable Spanish label
    allowed_instruments: tuple[str, ...]
    strategy_type: str
    stop_loss_pct: float  # e.g. 0.02 = 2%
    max_exposure_pct: float  # e.g. 0.20 = 20% of portfolio
    max_concurrent_positions: int


# ---------------------------------------------------------------------------
# Zone boundary constants
# ---------------------------------------------------------------------------
CONSERVATIVE_MAX = 35
MODERATE_MAX = 65

# ---------------------------------------------------------------------------
# Zone definitions (all values are inclusive boundaries)
# ---------------------------------------------------------------------------
_ZONES = {
    "conservative": {
        "zone_label": "Conservador",
        "allowed_instruments": (
            "ETF",
            "large-cap equity",
            "covered call",
        ),
        "strategy_type": "covered_calls",
        "stop_loss_pct": 0.02,
        "max_exposure_pct": 0.20,
        "max_concurrent_positions": 3,
    },
    "moderate": {
        "zone_label": "Moderado",
        "allowed_instruments": (
            "large-cap equity",
            "iron condor",
            "credit spread",
            "put spread",
            "call spread",
        ),
        "strategy_type": "iron_condors_credit_spreads",
        "stop_loss_pct": 0.05,
        "max_exposure_pct": 0.40,
        "max_concurrent_positions": 5,
    },
    "aggressive": {
        "zone_label": "Agresivo",
        "allowed_instruments": (
            "volatile equity",
            "large-cap equity",
            "crypto",
            "long call",
            "long put",
            "naked call",
            "naked put",
        ),
        "strategy_type": "directional_calls_puts",
        "stop_loss_pct": 0.10,
        "max_exposure_pct": 0.60,
        "max_concurrent_positions": 8,
    },
}


def _classify_zone(value: int) -> str:
    """Return the zone name for a given aggressiveness value (0-100)."""
    if value <= CONSERVATIVE_MAX:
        return "conservative"
    if value <= MODERATE_MAX:
        return "moderate"
    return "aggressive"


def get_aggressiveness_profile(value: int) -> AggressivenessProfile:
    """
    Pure function: maps an aggressiveness value (0-100) to a full trading profile.

    No I/O, no network calls, no database access. Fully deterministic.

    Args:
        value: Integer 0-100 representing the aggressiveness setting.

    Returns:
        AggressivenessProfile with zone info, allowed instruments, and risk limits.

    Raises:
        ValueError: If value is outside 0-100.
    """
    if not isinstance(value, int):
        raise TypeError(f"Aggressiveness value must be int, got {type(value).__name__}")
    if value < 0 or value > 100:
        raise ValueError(f"Aggressiveness value must be 0-100, got {value}")

    zone = _classify_zone(value)
    zone_def = _ZONES[zone]

    return AggressivenessProfile(
        value=value,
        zone=zone,
        zone_label=zone_def["zone_label"],
        allowed_instruments=zone_def["allowed_instruments"],
        strategy_type=zone_def["strategy_type"],
        stop_loss_pct=zone_def["stop_loss_pct"],
        max_exposure_pct=zone_def["max_exposure_pct"],
        max_concurrent_positions=zone_def["max_concurrent_positions"],
    )
