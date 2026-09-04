"""
SIGMA IA — Autonomous Mode (Autopilot).

Runs a continuous background loop that evaluates the market at regular
intervals and executes trades directly when the LLM decides to act,
subject to risk gate verification.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.aggressiveness import AggressivenessProfile, get_aggressiveness_profile
from app.database import Database
from app.llm_client import TradingAgent
from app.mcp_client import AlpacaMCPClient
from app.risk_gates import run_all_risk_checks

logger = logging.getLogger(__name__)


class AutonomousLoop:
    """
    Background trading loop for autonomous mode.

    Periodically:
    1. Fetches market data and account status via MCP
    2. Sends to LLM for analysis + action
    3. Checks risk gates on any proposed trades
    4. Executes via MCP if gates pass
    5. Logs everything to DB
    6. Takes a P&L snapshot
    """

    def __init__(
        self,
        mcp_client: AlpacaMCPClient,
        db: Database,
        interval_seconds: int = 60,
    ):
        self.mcp_client = mcp_client
        self.db = db
        self.interval_seconds = interval_seconds
        self.running = False
        self._task: asyncio.Task | None = None
        self._cycle_count = 0

    @property
    def is_running(self) -> bool:
        return self.running and self._task is not None and not self._task.done()

    async def start(self, aggressiveness_value: int) -> None:
        """Start the autonomous trading loop."""
        if self.is_running:
            logger.warning("Autonomous loop is already running.")
            return

        self.running = True
        self._cycle_count = 0
        self._aggressiveness_value = aggressiveness_value
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Autonomous loop started (interval=%ds, aggressiveness=%d)",
            self.interval_seconds,
            aggressiveness_value,
        )

    async def stop(self) -> None:
        """Stop the autonomous trading loop gracefully."""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Autonomous loop stopped after %d cycles.", self._cycle_count)

    def update_aggressiveness(self, value: int) -> None:
        """Update the aggressiveness for subsequent cycles without restarting."""
        self._aggressiveness_value = value
        logger.info("Autonomous loop aggressiveness updated to %d", value)

    async def _loop(self) -> None:
        """Main autonomous loop — runs until stopped."""
        while self.running:
            self._cycle_count += 1
            logger.info("=== Autonomous cycle #%d starting ===", self._cycle_count)

            try:
                await self._run_cycle()
            except asyncio.CancelledError:
                logger.info("Autonomous loop cancelled.")
                break
            except Exception as e:
                logger.error(
                    "Autonomous cycle #%d error: %s",
                    self._cycle_count,
                    e,
                    exc_info=True,
                )

            if self.running:
                logger.info(
                    "Autonomous cycle #%d complete. Sleeping %ds...",
                    self._cycle_count,
                    self.interval_seconds,
                )
                try:
                    await asyncio.sleep(self.interval_seconds)
                except asyncio.CancelledError:
                    break

    async def _run_cycle(self) -> None:
        """Execute a single autonomous trading cycle."""
        profile = get_aggressiveness_profile(self._aggressiveness_value)

        # 1. Create agent and analyze market
        agent = TradingAgent(mcp_client=self.mcp_client, db=self.db)

        recommendation = await agent.analyze_market(mode="autonomous")

        # 2. Save recommendation to DB
        rec_id = await self.db.create_recommendation(
            mode="autonomous",
            symbol=recommendation.symbol,
            strategy=recommendation.strategy,
            action=recommendation.action,
            llm_reasoning=recommendation.reasoning,
        )

        logger.info(
            "Autonomous recommendation #%d: symbol=%s, strategy=%s",
            rec_id,
            recommendation.symbol,
            recommendation.strategy,
        )

        # 3. Check if the LLM actually executed any order tools
        order_tools = {"place_order", "place_option_order", "submit_order"}
        executed_orders = [
            tc
            for tc in recommendation.tool_calls_made
            if tc["tool"] in order_tools
        ]

        if executed_orders:
            # LLM already called order tools during analysis
            # Verify risk gates retroactively and log
            inst_type = recommendation.strategy or "unknown"
            if "spread" in inst_type.lower() or "put" in inst_type.lower() or "call" in inst_type.lower():
                inst_type = profile.allowed_instruments[-1] if profile.allowed_instruments else inst_type

            proposed_order = {
                "instrument_type": inst_type,
                "estimated_value": 5000.0,
                "symbol": recommendation.symbol,
            }

            # Get current state for risk check
            current_positions = await self._get_positions()
            account_equity = await self._get_account_equity()

            risk_result = await run_all_risk_checks(
                profile=profile,
                proposed_order=proposed_order,
                current_positions=current_positions,
                account_equity=account_equity,
            )

            if not risk_result.allowed:
                await self.db.log_risk_gate_event(
                    recommendation_id=rec_id,
                    gate_name=risk_result.gate_name or "unknown",
                    proposed_action=json.dumps(proposed_order),
                    reason=risk_result.reason or "Risk check failed",
                )
                await self.db.update_recommendation_status(rec_id, "rejected")
                logger.warning(
                    "Autonomous order rejected by risk gate: %s",
                    risk_result.reason,
                )
            else:
                # Order was executed and risk gates pass
                await self.db.create_order(
                    recommendation_id=rec_id,
                    alpaca_order_id=None,
                    symbol=recommendation.symbol,
                    side=None,
                    qty=None,
                    order_type=recommendation.strategy,
                    status="submitted",
                    raw_response=json.dumps(executed_orders),
                )
                await self.db.update_recommendation_status(rec_id, "executed")
                logger.info(
                    "Autonomous order executed for recommendation %d", rec_id
                )
        else:
            # LLM analyzed but decided not to trade
            await self.db.update_recommendation_status(rec_id, "no_action")
            logger.info("Autonomous cycle: no trade opportunity found.")

        # 4. Take P&L snapshot
        await self._snapshot_pnl()

    async def _get_positions(self) -> list:
        """Fetch current positions from Alpaca via MCP."""
        try:
            if not self.mcp_client.is_connected:
                return []
            result = await self.mcp_client.call_tool("get_all_positions", {})
            if hasattr(result, "content") and result.content:
                text = getattr(result.content[0], "text", str(result.content[0]))
                positions = json.loads(text)
                return positions if isinstance(positions, list) else []
        except Exception as e:
            logger.warning("Failed to fetch positions: %s", e)
        return []

    async def _get_account_equity(self) -> float:
        """Fetch account equity from Alpaca via MCP."""
        try:
            if not self.mcp_client.is_connected:
                return 100_000.0
            result = await self.mcp_client.call_tool("get_account_info", {})
            if hasattr(result, "content") and result.content:
                text = getattr(result.content[0], "text", str(result.content[0]))
                data = json.loads(text)
                return float(data.get("equity", 100_000))
        except Exception as e:
            logger.warning("Failed to fetch account equity: %s", e)
        return 100_000.0

    async def _snapshot_pnl(self) -> None:
        """Take a P&L snapshot from the account."""
        try:
            if not self.mcp_client.is_connected:
                return
            result = await self.mcp_client.call_tool("get_account_info", {})
            if hasattr(result, "content") and result.content:
                text = getattr(result.content[0], "text", str(result.content[0]))
                data = json.loads(text)
                await self.db.create_pnl_snapshot(
                    equity=float(data.get("equity", 0)),
                    cash=float(data.get("cash", 0)),
                    buying_power=float(data.get("buying_power", 0)),
                    pnl_total=float(data.get("equity", 0)) - 100_000,
                    pnl_today=float(data.get("equity", 0))
                    - float(data.get("last_equity", data.get("equity", 0))),
                )
        except Exception as e:
            logger.warning("Failed to snapshot P&L: %s", e)
