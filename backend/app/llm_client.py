"""
SILVERCAWN — LLM Client (Gemini).

Handles the MCP tool-use loop with the google-genai SDK.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.mcp_client import AlpacaMCPClient
from app.risk_gates import run_all_risk_checks

logger = logging.getLogger(__name__)


def build_gemini_tools(mcp_tools: list[dict]) -> list[types.Tool]:
    """Convert MCP JSON schema tools to Gemini Tool declarations."""
    declarations = []
    for tool in mcp_tools:
        # MCP uses JSON Schema. Gemini's SDK typically accepts dicts that resemble OpenAPI schema.
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        
        # Ensure type is set and properties exists to avoid SDK errors
        if "type" not in schema:
            schema["type"] = "object"
        if "properties" not in schema:
            schema["properties"] = {}
            
        fd = types.FunctionDeclaration(
            name=tool["name"],
            description=tool.get("description", ""),
            parameters=schema
        )
        declarations.append(fd)
    
    if not declarations:
        return []
    
    return [types.Tool(function_declarations=declarations)]


class TradingAgent:
    """Agent that drives the Gemini + MCP tool-use loop."""

    def __init__(self, mcp_client: AlpacaMCPClient, db: Any = None):
        self.mcp = mcp_client
        self.db = db

        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY is not set.")
            self.client = None
        else:
            self.client = genai.Client(api_key=settings.gemini_api_key)
            
        self.model_id = settings.gemini_model

    async def analyze_market(self, mode: str) -> dict:
        """Run the main agent loop to generate a trading recommendation."""
        if not self.client:
            raise ConnectionError("Gemini API key not configured in .env")
        if not self.mcp.is_connected:
            raise RuntimeError("MCP client is not connected")

        # 1. Get MCP tools
        mcp_tools = await self.mcp.list_tools()
        gemini_tools = build_gemini_tools(mcp_tools)

        # 2. Prepare the system prompt
        system_instruction = (
            "You are SILVERCAWN, an elite autonomous options trading agent.\n"
            f"You are currently in {mode} mode.\n"
            "Analyze the market using the provided tools.\n"
            "If in 'asesor' mode, recommend a trade but DO NOT place an order.\n"
            "If in 'autonomo' mode, you MAY place orders using the order tools if conditions are right.\n"
            "ALWAYS output a final structured JSON summary using a text response formatted exactly as:\n"
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

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            temperature=0.0
        )

        # 3. Start the conversation loop
        history = [
            types.Content(
                role="user", 
                parts=[types.Part.from_text("Analyze the current account and market, then formulate a plan.")]
            )
        ]

        max_iterations = 10
        all_tool_calls_made = []
        for i in range(max_iterations):
            logger.info("Gemini LLM Loop iteration %d", i + 1)
            
            # Await the async gemini generation
            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=history,
                config=config
            )

            if not response.candidates:
                raise ValueError("No candidates returned from Gemini")
            
            candidate = response.candidates[0]
            if not candidate.content:
                raise ValueError("Candidate content is empty")

            # Append model's response to history
            history.append(candidate.content)

            # Check if there are tool calls
            tool_calls = []
            if candidate.content.parts:
                for part in candidate.content.parts:
                    if part.function_call:
                        tool_calls.append(part.function_call)
            
            if not tool_calls:
                # No tool calls, meaning LLM provided final text
                final_text = response.text or ""
                return self._parse_recommendation(final_text, all_tool_calls_made)

            # Execute tool calls
            tool_responses = []
            for function_call in tool_calls:
                name = function_call.name
                args = function_call.args if function_call.args else {}
                
                # IMPORTANT: Intercept order tools to enforce Risk Gates
                if "order" in name.lower() or "submit" in name.lower():
                    try:
                        from app.aggressiveness import get_aggressiveness_profile
                        from app.routes import _get_state
                        
                        state = _get_state()
                        profile = get_aggressiveness_profile(state.get("aggressiveness", 30))
                        
                        # Check equity
                        account_info = await self.mcp.call_tool("get_account", {})
                        equity = float(account_info.get("equity", 100000))
                        
                        risk_result = await run_all_risk_checks(
                            profile=profile,
                            proposed_order={"instrument_type": args.get("asset_class", "equity"), "estimated_value": 1000},
                            current_positions=[],
                            account_equity=equity,
                            current_exposure=0.0
                        )
                        
                        if not risk_result.allowed:
                            error_msg = f"RISK GATE BLOCKED: {risk_result.gate_name} - {risk_result.reason}"
                            logger.warning(error_msg)
                            tool_responses.append(
                                types.Part.from_function_response(
                                    name=name,
                                    response={"error": error_msg}
                                )
                            )
                            continue
                            
                    except Exception as e:
                        logger.error("Error running risk gates: %s", e)
                        
                # Call actual MCP tool
                try:
                    logger.info("LLM calling tool: %s", name)
                    # Handle arguments properly whether they are dicts or objects
                    args_dict = dict(args) if hasattr(args, "items") else {}
                    all_tool_calls_made.append({"tool": name, "args": args_dict})
                    result = await self.mcp.call_tool(name, args_dict)
                    
                    tool_responses.append(
                        types.Part.from_function_response(
                            name=name,
                            response={"result": result}
                        )
                    )
                except Exception as e:
                    logger.error("Tool execution failed: %s", e)
                    tool_responses.append(
                        types.Part.from_function_response(
                            name=name,
                            response={"error": str(e)}
                        )
                    )
            
            # Send tool responses back to model as a "user" role turn or "function" role
            # Google GenAI requires tool responses to come from role "user" typically.
            history.append(
                types.Content(
                    role="user",
                    parts=tool_responses
                )
            )

        raise RuntimeError("LLM Loop exceeded max iterations without a final answer.")

    def _parse_recommendation(self, text: str, tool_calls_made: list) -> Any:
        """Extract JSON from LLM text and return an object."""
        class Recommendation:
            def __init__(self, data, tools):
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
                block = block[start:end+1]
                
            data = json.loads(block)
            return Recommendation(data, tool_calls_made)
        except Exception as e:
            logger.error("Failed to parse recommendation JSON: %s\nText was: %s", e, text)
            return Recommendation({"llm_reasoning": text}, tool_calls_made)
