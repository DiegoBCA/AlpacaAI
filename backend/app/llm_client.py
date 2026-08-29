"""
SILVERCAWN — LLM Client (NVIDIA AI).

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
            raise RuntimeError("MCP client is not connected")

        # 1. Get MCP tools
        mcp_tools = await self.mcp.list_tools()
        openai_tools = build_openai_tools(mcp_tools)

        # 2. System prompt
        system_prompt = (
            "You are SILVERCAWN, an elite autonomous options trading agent.\n"
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

            response = await self.client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            message = choice.message

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
            result = await self.mcp.call_tool("get_account", {})
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
