"""
SILVERCAWN — MCP Client for Alpaca MCP Server.

Manages the lifecycle of the Alpaca MCP Server subprocess (stdio transport)
and provides methods to list/call tools.
"""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings

logger = logging.getLogger(__name__)


class AlpacaMCPClient:
    """
    Async MCP client that connects to the Alpaca MCP Server via stdio.

    Usage:
        client = AlpacaMCPClient()
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("tool_name", {"arg": "value"})
        await client.disconnect()
    """

    def __init__(self):
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._tools_cache: list[dict] | None = None

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect(self) -> None:
        """Start the Alpaca MCP Server subprocess and initialize the session."""
        if self.is_connected:
            logger.warning("MCP client already connected.")
            return

        if not settings.validate_alpaca_keys():
            logger.error(
                "Alpaca API keys not configured. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
            )
            raise ConnectionError("Alpaca API keys not configured in .env")

        # Build environment for the MCP server subprocess
        env = {
            **os.environ,
            "ALPACA_API_KEY": settings.alpaca_api_key,
            "ALPACA_SECRET_KEY": settings.alpaca_secret_key,
            "ALPACA_PAPER_TRADE": "true",  # Always paper trading
            "ALPACA_TOOLSETS": "options-data,trading,assets",
        }

        server_params = StdioServerParameters(
            command="uvx",
            args=["alpaca-mcp-server"],
            env=env,
        )

        logger.info("Starting Alpaca MCP Server via uvx...")

        self._exit_stack = AsyncExitStack()

        try:
            # Start the stdio client (spawns the subprocess)
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )

            # Create and initialize the session
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()

            # Cache the tools list
            tools_result = await self._session.list_tools()
            self._tools_cache = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in tools_result.tools
            ]

            logger.info(
                "MCP client connected. %d tools available.", len(self._tools_cache)
            )
        except Exception as e:
            logger.error("Failed to connect MCP client: %s", e)
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Cleanly shut down the MCP server subprocess."""
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.warning("Error during MCP disconnect: %s", e)
            finally:
                self._session = None
                self._exit_stack = None
                self._tools_cache = None
                logger.info("MCP client disconnected.")

    async def list_tools(self) -> list[dict]:
        """
        Return tool definitions formatted for the Anthropic API.

        Returns a list of dicts with 'name', 'description', and 'input_schema' keys.
        """
        if self._tools_cache is not None:
            return self._tools_cache

        if not self.is_connected:
            raise RuntimeError("MCP client not connected. Call connect() first.")

        tools_result = await self._session.list_tools()  # type: ignore[union-attr]
        self._tools_cache = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in tools_result.tools
        ]
        return self._tools_cache

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """
        Execute a tool on the Alpaca MCP Server.

        Args:
            name: The tool name (as returned by list_tools).
            arguments: Dict of arguments to pass to the tool.

        Returns:
            The tool result from the MCP server.
        """
        if not self.is_connected:
            raise RuntimeError("MCP client not connected. Call connect() first.")

        logger.info("Calling MCP tool: %s with args: %s", name, arguments)

        result = await self._session.call_tool(name, arguments=arguments)  # type: ignore[union-attr]

        logger.info("MCP tool %s returned result.", name)
        return result
