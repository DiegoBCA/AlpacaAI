"""
Tests for MCP Server Integration.

Uses mocks when Alpaca credentials are not available.
Tests actual connection when credentials are configured.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.mcp_client import AlpacaMCPClient


class TestMCPClientUnit:
    """Unit tests using mocks — no real credentials needed."""

    def test_initial_state(self):
        client = AlpacaMCPClient()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_fails_without_keys(self):
        """Should raise ConnectionError when API keys are empty."""
        with patch("app.mcp_client.settings") as mock_settings:
            mock_settings.validate_alpaca_keys.return_value = False
            client = AlpacaMCPClient()
            with pytest.raises(ConnectionError, match="API keys not configured"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_list_tools_without_connection_raises(self):
        """Should raise RuntimeError if not connected."""
        client = AlpacaMCPClient()
        client._tools_cache = None
        with pytest.raises(RuntimeError, match="not connected"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_call_tool_without_connection_raises(self):
        """Should raise RuntimeError if not connected."""
        client = AlpacaMCPClient()
        with pytest.raises(RuntimeError, match="not connected"):
            await client.call_tool("test_tool", {})

    @pytest.mark.asyncio
    async def test_list_tools_returns_cached(self):
        """Should return cached tools without hitting MCP."""
        client = AlpacaMCPClient()
        client._tools_cache = [
            {"name": "get_account_info", "description": "Get account info", "input_schema": {}}
        ]
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "get_account_info"

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self):
        """Disconnect should reset all state."""
        client = AlpacaMCPClient()
        client._tools_cache = [{"name": "test"}]
        client._exit_stack = AsyncMock()
        client._session = MagicMock()

        await client.disconnect()

        assert client._session is None
        assert client._exit_stack is None
        assert client._tools_cache is None
        assert client.is_connected is False


class TestMCPClientIntegration:
    """
    Integration tests — only run when ALPACA_API_KEY is set.

    These tests verify actual connectivity to the Alpaca MCP Server.
    """

    @pytest.fixture
    def has_credentials(self):
        """Skip tests if credentials are not available."""
        if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
            pytest.skip("Alpaca credentials not configured — skipping integration test")

    @pytest.mark.asyncio
    async def test_connect_and_list_tools(self, has_credentials):
        """Verify we can connect and discover tools."""
        client = AlpacaMCPClient()
        try:
            await client.connect()
            assert client.is_connected

            tools = await client.list_tools()
            assert len(tools) > 0

            # Verify essential tools exist
            tool_names = {t["name"] for t in tools}
            # These should exist in the Alpaca MCP Server
            assert "get_account_info" in tool_names or any(
                "account" in name for name in tool_names
            ), f"No account tool found. Available: {tool_names}"

        finally:
            await client.disconnect()
            assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_tools_have_correct_structure(self, has_credentials):
        """Verify tool definitions have the expected schema for Anthropic."""
        client = AlpacaMCPClient()
        try:
            await client.connect()
            tools = await client.list_tools()

            for tool in tools:
                assert "name" in tool, f"Tool missing 'name': {tool}"
                assert "description" in tool, f"Tool missing 'description': {tool}"
                assert "input_schema" in tool, f"Tool missing 'input_schema': {tool}"
                assert isinstance(tool["name"], str)
        finally:
            await client.disconnect()
