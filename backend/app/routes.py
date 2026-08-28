"""
SILVERCAWN — FastAPI Routes.

All REST API endpoints for the trading agent.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.aggressiveness import get_aggressiveness_profile

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class AggressivenessRequest(BaseModel):
    value: int = Field(..., ge=0, le=100, description="Aggressiveness 0-100")


class ModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(asesor|autonomo)$", description="asesor or autonomo")


class StatusResponse(BaseModel):
    mode: str
    aggressiveness: int
    zone: str
    zone_label: str
    mcp_connected: bool
    autonomous_running: bool


# ---------------------------------------------------------------------------
# Dependency: app state is injected from main.py's lifespan
# ---------------------------------------------------------------------------
# These will be set by main.py after startup
_app_state: dict = {}


def set_app_state(state: dict) -> None:
    """Called by main.py to inject shared state."""
    global _app_state
    _app_state = state


def _get_state():
    return _app_state


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current system status."""
    state = _get_state()
    profile = get_aggressiveness_profile(state.get("aggressiveness", 30))
    return StatusResponse(
        mode=state.get("mode", "asesor"),
        aggressiveness=state.get("aggressiveness", 30),
        zone=profile.zone,
        zone_label=profile.zone_label,
        mcp_connected=state.get("mcp_client") is not None
        and state["mcp_client"].is_connected,
        autonomous_running=state.get("autonomous_loop") is not None
        and state["autonomous_loop"].is_running,
    )


@router.get("/aggressiveness")
async def get_aggressiveness():
    """Get current aggressiveness value and full profile."""
    state = _get_state()
    value = state.get("aggressiveness", 30)
    profile = get_aggressiveness_profile(value)
    return {
        "value": profile.value,
        "zone": profile.zone,
        "zone_label": profile.zone_label,
        "allowed_instruments": list(profile.allowed_instruments),
        "strategy_type": profile.strategy_type,
        "stop_loss_pct": profile.stop_loss_pct,
        "max_exposure_pct": profile.max_exposure_pct,
        "max_concurrent_positions": profile.max_concurrent_positions,
    }


@router.post("/aggressiveness")
async def set_aggressiveness(req: AggressivenessRequest):
    """Set the aggressiveness level (0-100)."""
    state = _get_state()
    db = state.get("db")

    # Validate and get profile
    profile = get_aggressiveness_profile(req.value)

    # Update in-memory state
    state["aggressiveness"] = req.value

    # Update autonomous loop if running
    autonomous = state.get("autonomous_loop")
    if autonomous and autonomous.is_running:
        autonomous.update_aggressiveness(req.value)

    # Log to database
    if db:
        await db.log_aggressiveness(req.value, profile.zone)

    logger.info("Aggressiveness set to %d (%s)", req.value, profile.zone)

    return {
        "value": profile.value,
        "zone": profile.zone,
        "zone_label": profile.zone_label,
        "message": f"Aggressiveness set to {req.value}% ({profile.zone_label})",
    }


@router.post("/mode")
async def set_mode(req: ModeRequest):
    """Switch between advisor (asesor) and autonomous (autonomo) modes."""
    state = _get_state()
    autonomous = state.get("autonomous_loop")
    old_mode = state.get("mode", "asesor")

    if req.mode == old_mode:
        return {"mode": req.mode, "message": f"Already in {req.mode} mode."}

    state["mode"] = req.mode

    if req.mode == "autonomo":
        # Start autonomous loop
        if autonomous and not autonomous.is_running:
            aggressiveness = state.get("aggressiveness", 30)
            try:
                await autonomous.start(aggressiveness)
                logger.info("Autonomous mode activated.")
            except Exception as e:
                logger.error("Failed to start autonomous mode: %s", e)
                state["mode"] = "asesor"
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to start autonomous mode: {e}",
                )
    else:
        # Stop autonomous loop
        if autonomous and autonomous.is_running:
            await autonomous.stop()
            logger.info("Autonomous mode deactivated, switched to advisor.")

    return {"mode": req.mode, "message": f"Mode switched to {req.mode}."}


@router.get("/recommendations")
async def list_recommendations(status: Optional[str] = None):
    """List recommendations, optionally filtered by status."""
    state = _get_state()
    db = state.get("db")
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    recs = await db.list_recommendations(status=status)
    return {"recommendations": recs}


@router.post("/recommendations/{rec_id}/approve")
async def approve_recommendation_endpoint(rec_id: int):
    """Approve a pending recommendation and attempt to execute the order."""
    state = _get_state()
    db = state.get("db")
    mcp_client = state.get("mcp_client")
    aggressiveness = state.get("aggressiveness", 30)

    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    from app.advisor import approve_recommendation

    profile = get_aggressiveness_profile(aggressiveness)

    try:
        result = await approve_recommendation(
            rec_id=rec_id,
            mcp_client=mcp_client,
            profile=profile,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error approving recommendation %d: %s", rec_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def list_orders():
    """List order history."""
    state = _get_state()
    db = state.get("db")
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    orders = await db.list_orders()
    return {"orders": orders}


@router.post("/cycle")
async def trigger_cycle():
    """Manually trigger a single analysis cycle (useful for testing)."""
    state = _get_state()
    db = state.get("db")
    mcp_client = state.get("mcp_client")
    mode = state.get("mode", "asesor")
    aggressiveness = state.get("aggressiveness", 30)

    if not db:
        raise HTTPException(status_code=503, detail="Database not available")
    if not mcp_client or not mcp_client.is_connected:
        raise HTTPException(status_code=503, detail="MCP client not connected")

    from app.advisor import run_advisor_cycle

    profile = get_aggressiveness_profile(aggressiveness)

    try:
        result = await run_advisor_cycle(
            mcp_client=mcp_client,
            profile=profile,
            db=db,
        )
        return result
    except Exception as e:
        logger.error("Cycle error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pnl")
async def get_pnl():
    """Get P&L snapshots."""
    state = _get_state()
    db = state.get("db")
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    snapshots = await db.list_pnl_snapshots()
    return {"snapshots": snapshots}


@router.get("/risk-events")
async def get_risk_events():
    """Get risk gate event history."""
    state = _get_state()
    db = state.get("db")
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    events = await db.list_risk_gate_events()
    return {"events": events}
