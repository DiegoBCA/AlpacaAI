"""
SILVERCAWN — Advisor Mode (Copilot).

Runs a single analysis cycle where the LLM recommends a trade but does NOT
execute it. The recommendation is saved with status='pending' and must be
explicitly approved via the API to send the order.
"""

from __future__ import annotations

import json
import logging

from app.aggressiveness import AggressivenessProfile
from app.database import Database
from app.llm_client import TradingAgent
from app.mcp_client import AlpacaMCPClient
from app.risk_gates import run_all_risk_checks

logger = logging.getLogger(__name__)


async def run_advisor_cycle(
    mcp_client: AlpacaMCPClient,
    profile: AggressivenessProfile,
    db: Database,
) -> dict:
    """
    Execute one advisor cycle:
    1. Create an LLM agent in advisor mode
    2. Analyze the market (LLM uses MCP data tools only)
    3. Save the recommendation with status='pending'
    4. Return the recommendation data

    Returns:
        Dict with recommendation id and details.
    """
    logger.info(
        "Starting advisor cycle (aggressiveness=%d, zone=%s)",
        profile.value,
        profile.zone,
    )

    agent = TradingAgent(mcp_client=mcp_client, db=db)

    try:
        recommendation = await agent.analyze_market(mode="advisor")
    except Exception as e:
        logger.error("Advisor cycle failed during market analysis: %s", e)
        raise

    # Save to database
    rec_id = await db.create_recommendation(
        mode="advisor",
        symbol=recommendation.symbol,
        strategy=recommendation.strategy,
        action=recommendation.action,
        llm_reasoning=recommendation.reasoning,
    )

    logger.info(
        "Advisor recommendation saved: id=%d, symbol=%s, strategy=%s",
        rec_id,
        recommendation.symbol,
        recommendation.strategy,
    )

    return {
        "id": rec_id,
        "mode": "advisor",
        "symbol": recommendation.symbol,
        "strategy": recommendation.strategy,
        "action": recommendation.action,
        "reasoning": recommendation.reasoning,
        "status": "pending",
        "tool_calls": recommendation.tool_calls_made,
    }


async def approve_recommendation(
    rec_id: int,
    mcp_client: AlpacaMCPClient,
    profile: AggressivenessProfile,
    db: Database,
) -> dict:
    """
    Approve a pending recommendation and attempt to execute the order.

    Steps:
    1. Load recommendation from DB
    2. Verify it's still 'pending'
    3. Run risk gates
    4. If gates pass → execute via MCP
    5. Save order to DB + update recommendation status

    Returns:
        Dict with order status and details.
    """
    # Load the recommendation
    rec = await db.get_recommendation(rec_id)
    if not rec:
        raise ValueError(f"Recommendation {rec_id} not found")

    if rec["status"] != "pending":
        raise ValueError(
            f"Recommendation {rec_id} is '{rec['status']}', not 'pending'"
        )

    logger.info("Approving recommendation %d: %s", rec_id, rec["action"])

    # Build a proposed order from the recommendation
    proposed_order = {
        "instrument_type": rec.get("strategy") or "unknown",
        "estimated_value": 5000.0,  # Default estimate — will be refined in later phases
        "symbol": rec.get("symbol"),
    }

    # Get current positions via MCP (best-effort)
    current_positions: list = []
    account_equity = 100_000.0  # Default for paper account

    try:
        if mcp_client.is_connected:
            # Try to get actual positions
            positions_result = await mcp_client.call_tool("get_positions", {})
            if hasattr(positions_result, "content") and positions_result.content:
                positions_text = getattr(
                    positions_result.content[0],
                    "text",
                    str(positions_result.content[0]),
                )
                try:
                    current_positions = json.loads(positions_text)
                    if not isinstance(current_positions, list):
                        current_positions = []
                except (json.JSONDecodeError, TypeError):
                    current_positions = []

            # Try to get account info
            account_result = await mcp_client.call_tool("get_account", {})
            if hasattr(account_result, "content") and account_result.content:
                account_text = getattr(
                    account_result.content[0],
                    "text",
                    str(account_result.content[0]),
                )
                try:
                    account_data = json.loads(account_text)
                    account_equity = float(account_data.get("equity", 100_000))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
    except Exception as e:
        logger.warning("Could not fetch positions/account for risk check: %s", e)

    # Run risk gates
    risk_result = await run_all_risk_checks(
        profile=profile,
        proposed_order=proposed_order,
        current_positions=current_positions,
        account_equity=account_equity,
    )

    if not risk_result.allowed:
        # Risk gate blocked the order
        await db.log_risk_gate_event(
            recommendation_id=rec_id,
            gate_name=risk_result.gate_name or "unknown",
            proposed_action=json.dumps(proposed_order),
            reason=risk_result.reason or "Unknown risk gate failure",
        )
        await db.update_recommendation_status(rec_id, "rejected")

        logger.warning(
            "Recommendation %d rejected by risk gate: %s", rec_id, risk_result.reason
        )
        return {
            "id": rec_id,
            "status": "rejected",
            "reason": risk_result.reason,
            "gate": risk_result.gate_name,
        }

    # Risk gates passed — attempt to execute via MCP directly
    try:
        # Determine order side from the recommendation action
        action_str = (rec.get("action") or "").lower()
        side = "buy" if "buy" in action_str else "sell"

        # Place order via MCP
        order_args = {
            "symbol": rec.get("symbol", ""),
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "qty": "1",  # Conservative default for paper trading
        }

        order_result = None
        try:
            result = await mcp_client.call_tool("place_order", order_args)
            if hasattr(result, "content") and result.content:
                order_result = getattr(
                    result.content[0], "text", str(result.content[0])
                )
            else:
                order_result = str(result)
        except Exception as e:
            order_result = f"Order execution error: {e}"
            logger.error("Order execution via MCP failed: %s", e)

        # Save order to DB
        order_id = await db.create_order(
            recommendation_id=rec_id,
            alpaca_order_id=None,  # Will be parsed from result in future phases
            symbol=rec.get("symbol"),
            side=side,
            qty=1.0,
            order_type=rec.get("strategy"),
            status="submitted",
            raw_response=order_result,
        )

        await db.update_recommendation_status(rec_id, "executed")

        logger.info(
            "Recommendation %d executed, order %d created", rec_id, order_id
        )
        return {
            "id": rec_id,
            "status": "executed",
            "order_id": order_id,
            "order_result": order_result,
        }

    except Exception as e:
        logger.error("Failed to execute recommendation %d: %s", rec_id, e)
        await db.update_recommendation_status(rec_id, "failed")
        await db.create_order(
            recommendation_id=rec_id,
            alpaca_order_id=None,
            symbol=rec.get("symbol"),
            side=None,
            qty=None,
            order_type=rec.get("strategy"),
            status="failed",
            raw_response=str(e),
        )
        return {
            "id": rec_id,
            "status": "failed",
            "error": str(e),
        }
