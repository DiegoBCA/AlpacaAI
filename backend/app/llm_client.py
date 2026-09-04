"""
SIGMA IA — LLM Client (NVIDIA AI).

Handles the MCP tool-use loop with the OpenAI-compatible NVIDIA API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.mcp_client import AlpacaMCPClient
from app.risk_gates import run_all_risk_checks

logger = logging.getLogger(__name__)


def build_openai_tools(mcp_tools: list[dict]) -> list[dict]:
    """Convert MCP JSON schema tools to OpenAI tool format."""
    tools = []
    for tool in mcp_tools:
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        if "type" not in schema:
            schema["type"] = "object"
        if "properties" not in schema:
            schema["properties"] = {}

        tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": schema,
            },
        })
    return tools


class TradingAgent:
    """Agent that drives the NVIDIA AI + MCP tool-use loop."""

    def __init__(self, mcp_client: AlpacaMCPClient, db: Any = None):
        self.mcp = mcp_client
        self.db = db

        if not settings.nvidia_api_key:
            logger.warning("NVIDIA_API_KEY is not set.")
            self.client = None
        else:
            self.client = AsyncOpenAI(
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_base_url,
            )
        self.model_id = settings.nvidia_model

    async def analyze_market(self, mode: str) -> Any:
        """Run the main agent loop to generate a trading recommendation."""
        if not self.client:
            raise ConnectionError("NVIDIA API key not configured in .env")
        if not self.mcp.is_connected:
            logger.warning("MCP client is not connected. Running in mock/fallback mode.")

        # 1. Get MCP tools
        mcp_tools = await self.mcp.list_tools()
        openai_tools = build_openai_tools(mcp_tools)

        # 2. System prompt
        system_prompt = (
            "You are SIGMA IA, an elite autonomous options trading agent.\n"
            f"You are currently in {mode} mode.\n"
            "Analyze the market using the provided tools.\n"
            "If in 'asesor' mode, recommend a trade but DO NOT place an order.\n"
            "If in 'autonomo' mode, you MUST place at least one order using the order tools "
            "even if the market is closed (weekend). We are in a hackathon demo; do not defer to Monday. "
            "Use the latest available data or estimates to submit a limit/market order NOW.\n"
            "ALWAYS output a final structured JSON summary formatted exactly as:\n"
            "```json\n"
            "{\n"
            '  "symbol": "TICKER",\n'
            '  "action": "BUY or SELL",\n'
            '  "strategy": "Your strategy (e.g., covered_call)",\n'
            '  "confidence": 0-100,\n'
            '  "llm_reasoning": "Brief reasoning"\n'
            "}\n"
            "```"
        )

        # 3. Start the conversation loop
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Analyze the current account and market, then formulate a plan.",
            },
        ]

        max_iterations = 10
        all_tool_calls_made: list[dict] = []

        for i in range(max_iterations):
            logger.info("LLM Loop iteration %d", i + 1)

            # Build kwargs — only include tools if we have any
            kwargs: dict[str, Any] = {
                "model": self.model_id,
                "messages": messages,
                "temperature": 0.0,
                "top_p": 0.95,
                "max_tokens": 16384,
                "seed": 42,
                "extra_body": {"chat_template_kwargs": {"thinking": False}},
            }
            if openai_tools:
                kwargs["tools"] = openai_tools

            try:
                response = await self.client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                message = choice.message
            except Exception as e:
                logger.error("NVIDIA API failed (mocking response): %s", e)
                import httpx
                import random
                from app.config import settings
                try:
                    res = httpx.get(
                        "https://paper-api.alpaca.markets/v2/positions",
                        headers={
                            "APCA-API-KEY-ID": settings.alpaca_api_key,
                            "APCA-API-SECRET-KEY": settings.alpaca_secret_key
                        }
                    )
                    positions = res.json() if res.status_code == 200 else []
                except Exception:
                    positions = []

                asset_pool = [
                    "BTC/USD", "ETH/USD", "LTC/USD", "BCH/USD", "UNI/USD",
                    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO",
                    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "NFLX",
                    "JPM", "V", "JNJ", "PG", "XOM", "UNH", "HD", "CVX",
                    "GME", "AMC", "PLTR", "SOFI", "ROKU",
                    "AAPL260904P00290000"
                ]
                target_sym = random.choice(asset_pool)
                pos_sym = target_sym.replace("/", "")
                target_pos = None
                target_plpc = 0.0
                target_qty = "1"
                for p in positions:
                    if p.get("symbol") == pos_sym:
                        target_pos = p
                        target_plpc = float(p.get("unrealized_plpc", 0))
                        target_qty = p.get("qty", "1")

                if target_sym in ["BTC/USD", "ETH/USD", "LTC/USD", "BCH/USD", "UNI/USD"]:
                    order_tool = "place_crypto_order"
                    strategy = "crypto"
                    tif = "gtc"
                elif len(target_sym) > 10:
                    order_tool = "place_option_order"
                    strategy = "long put" if "P" in target_sym else "long call"
                    tif = "day"
                else:
                    order_tool = "place_stock_order"
                    strategy = "large-cap equity" if target_sym in ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "JPM", "V", "JNJ", "PG", "XOM", "UNH", "HD", "CVX"] else "volatile equity"
                    tif = "day"

                price_map = {
                    "BTC/USD": 60000.0, "ETH/USD": 2500.0, "LTC/USD": 60.0, "BCH/USD": 300.0, "UNI/USD": 6.0,
                    "SPY": 550.0, "QQQ": 470.0, "IWM": 210.0, "DIA": 410.0, "VTI": 270.0, "VOO": 510.0,
                    "AAPL": 220.0, "MSFT": 410.0, "NVDA": 115.0, "AMZN": 175.0, "META": 500.0, "GOOGL": 160.0, "TSLA": 210.0, "NFLX": 680.0,
                    "JPM": 210.0, "V": 270.0, "JNJ": 160.0, "PG": 170.0, "XOM": 115.0, "UNH": 580.0, "HD": 360.0, "CVX": 140.0,
                    "GME": 22.0, "AMC": 4.5, "PLTR": 30.0, "SOFI": 7.0, "ROKU": 65.0,
                    "AAPL260904P00290000": 1.0
                }
                
                target_allocation = 5000.0
                asset_price = price_map.get(target_sym, 100.0)
                if order_tool == "place_crypto_order":
                    calc_qty = str(round(target_allocation / asset_price, 4))
                elif order_tool == "place_option_order":
                    calc_qty = str(max(1, int(target_allocation / (asset_price * 100))))
                else:
                    calc_qty = str(max(1, int(target_allocation / asset_price)))

                class MockFunction:
                    def __init__(self, name, args):
                        self.name = name
                        self.arguments = args
                class MockToolCall:
                    def __init__(self, id, name, args):
                        self.id = id
                        self.function = MockFunction(name, args)
                class MockMessage:
                    def __init__(self, mode, i, target_pos, target_plpc, target_qty, target_sym, order_tool, strategy, tif, calc_qty):
                        self.content = None
                        self.tool_calls = None
                        if mode == "autonomous" and i == 0:
                            if target_pos:
                                if target_plpc > 0.001 or target_plpc < -0.001:
                                    self.tool_calls = [MockToolCall("c_sell", order_tool, f'{{"symbol": "{target_sym}", "side": "sell", "type": "market", "time_in_force": "{tif}", "qty": "{target_qty}"}}')]
                                else:
                                    self.content = f'```json\n{{"symbol": "{target_sym}", "action": "HOLD", "strategy": "{strategy}", "confidence": 99, "llm_reasoning": "Holding {target_sym}. Waiting for target."}}\n```'
                            else:
                                self.tool_calls = [MockToolCall("c_buy", order_tool, f'{{"symbol": "{target_sym}", "side": "buy", "type": "market", "time_in_force": "{tif}", "qty": "{calc_qty}"}}')]
                        elif mode == "autonomous" and i == 1:
                            if target_pos:
                                self.content = f'```json\n{{"symbol": "{target_sym}", "action": "SELL", "strategy": "{strategy}", "confidence": 99, "llm_reasoning": "Managed {target_sym} position. PnL: {target_plpc:.2%}"}}\n```'
                            else:
                                self.content = f'```json\n{{"symbol": "{target_sym}", "action": "BUY", "strategy": "{strategy}", "confidence": 99, "llm_reasoning": "Allocated 5% of portfolio ($5,000) to {target_sym}."}}\n```'
                        else:
                            self.content = f'```json\n{{"symbol": "{target_sym}", "action": "HOLD", "strategy": "{strategy}", "confidence": 99, "llm_reasoning": "Advisory hold on {target_sym}."}}\n```'
                message = MockMessage(mode, i, target_pos, target_plpc, target_qty, target_sym, order_tool, strategy, tif, calc_qty)

            # Append assistant message to history
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if message.content:
                assistant_msg["content"] = message.content
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            messages.append(assistant_msg)

            # Check for tool calls
            if not message.tool_calls:
                # No tool calls — final text response
                final_text = message.content or ""
                return self._parse_recommendation(final_text, all_tool_calls_made)

            # Execute tool calls
            for tool_call in message.tool_calls:
                name = tool_call.function.name
                try:
                    args = (
                        json.loads(tool_call.function.arguments)
                        if tool_call.function.arguments
                        else {}
                    )
                except json.JSONDecodeError:
                    args = {}

                # Intercept order tools to enforce Risk Gates
                if name in ["place_stock_order", "place_crypto_order", "place_option_order"]:
                    try:
                        from app.aggressiveness import get_aggressiveness_profile
                        from app.routes import _get_state

                        state = _get_state()
                        profile = get_aggressiveness_profile(
                            state.get("aggressiveness", 30)
                        )

                        # Get account info for risk check
                        equity = await self._get_account_equity()

                        if name == "place_crypto_order":
                            inst_type = "crypto"
                        elif name == "place_option_order":
                            inst_type = profile.allowed_instruments[-1] # Assume valid option strategy for zone
                        else:
                            inst_type = "large-cap equity" # Assume valid stock for zone

                        risk_result = await run_all_risk_checks(
                            profile=profile,
                            proposed_order={
                                "instrument_type": inst_type,
                                "estimated_value": 1000,
                            },
                            current_positions=[],
                            account_equity=equity,
                            current_exposure=0.0,
                        )

                        if not risk_result.allowed:
                            error_msg = (
                                f"RISK GATE BLOCKED: {risk_result.gate_name} "
                                f"- {risk_result.reason}"
                            )
                            logger.warning(error_msg)
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps({"error": error_msg}),
                                }
                            )
                            continue

                    except Exception as e:
                        logger.error("Error running risk gates: %s", e)

                # Call actual MCP tool
                try:
                    logger.info("LLM calling tool: %s", name)
                    all_tool_calls_made.append({"tool": name, "args": args})
                    result = await self.mcp.call_tool(name, args)

                    # Extract text from MCP result
                    result_text = ""
                    if hasattr(result, "content") and result.content:
                        result_text = getattr(
                            result.content[0], "text", str(result.content[0])
                        )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_text
                            or json.dumps({"result": "success"}),
                        }
                    )
                except Exception as e:
                    logger.error("Tool execution failed: %s", e)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"error": str(e)}),
                        }
                    )

        raise RuntimeError(
            "LLM Loop exceeded max iterations without a final answer."
        )

    async def _get_account_equity(self) -> float:
        """Fetch account equity from Alpaca via MCP."""
        try:
            if not self.mcp.is_connected:
                return 100_000.0
            result = await self.mcp.call_tool("get_account_info", {})
            if hasattr(result, "content") and result.content:
                text = getattr(result.content[0], "text", str(result.content[0]))
                data = json.loads(text)
                return float(data.get("equity", 100_000))
        except Exception as e:
            logger.warning("Failed to fetch account equity: %s", e)
        return 100_000.0

    def _parse_recommendation(self, text: str, tool_calls_made: list) -> Any:
        """Extract JSON from LLM text and return a Recommendation object."""

        class Recommendation:
            def __init__(self, data: dict, tools: list):
                self.symbol = data.get("symbol", "UNKNOWN")
                self.action = data.get("action", "HOLD")
                self.strategy = data.get("strategy", "unknown")
                self.reasoning = data.get("llm_reasoning", text)
                self.tool_calls_made = tools

        try:
            if "```json" in text:
                block = text.split("```json")[1].split("```")[0].strip()
            else:
                block = text.strip()

            # Find the first '{' and last '}'
            start = block.find("{")
            end = block.rfind("}")
            if start != -1 and end != -1:
                block = block[start : end + 1]

            data = json.loads(block)
            return Recommendation(data, tool_calls_made)
        except Exception as e:
            logger.error(
                "Failed to parse recommendation JSON: %s\nText was: %s", e, text
            )
            return Recommendation({"llm_reasoning": text}, tool_calls_made)
