"""
SIGMA IA — FastAPI Application Entry Point.

Handles application lifecycle (startup/shutdown), CORS, and router mounting.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.autonomous import AutonomousLoop
from app.config import settings
from app.database import Database
from app.mcp_client import AlpacaMCPClient
from app.routes import router, set_app_state

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sigma_ia")


# ---------------------------------------------------------------------------
# Shared application state
# ---------------------------------------------------------------------------
app_state: dict = {
    "mode": "asesor",
    "aggressiveness": 30,
    "db": None,
    "mcp_client": None,
    "autonomous_loop": None,
}


# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of all services."""
    logger.info("=" * 60)
    logger.info("SIGMA IA Trading Agent starting up...")
    logger.info("=" * 60)

    # 1. Initialize database
    db = Database(db_path=settings.database_path)
    await db.connect()
    app_state["db"] = db

    # Load last aggressiveness from DB (if any)
    last_agg = await db.get_current_aggressiveness()
    if last_agg:
        app_state["aggressiveness"] = last_agg["value"]
        logger.info("Restored aggressiveness: %d", last_agg["value"])
    else:
        # Log initial default
        from app.aggressiveness import get_aggressiveness_profile

        profile = get_aggressiveness_profile(app_state["aggressiveness"])
        await db.log_aggressiveness(app_state["aggressiveness"], profile.zone)

    # 2. Initialize MCP client (best-effort — don't block startup)
    mcp_client = AlpacaMCPClient()
    app_state["mcp_client"] = mcp_client

    if settings.validate_alpaca_keys():
        try:
            await mcp_client.connect()
            logger.info("MCP client connected successfully.")
        except Exception as e:
            logger.warning(
                "MCP client connection failed (will retry on demand): %s", e
            )
    else:
        logger.warning(
            "Alpaca API keys not configured. MCP client not connected. "
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
        )

    # 3. Initialize autonomous loop (but don't start it — starts via API)
    autonomous_loop = AutonomousLoop(
        mcp_client=mcp_client,
        db=db,
        interval_seconds=settings.autonomous_interval_seconds,
    )
    app_state["autonomous_loop"] = autonomous_loop

    # 4. Inject state into routes
    set_app_state(app_state)

    logger.info("SIGMA IA ready. Mode=%s, Aggressiveness=%d",
                app_state["mode"], app_state["aggressiveness"])
    logger.info("API docs: http://localhost:8000/docs")

    yield  # --- App is running ---

    # Shutdown
    logger.info("SIGMA IA shutting down...")

    if autonomous_loop.is_running:
        await autonomous_loop.stop()

    if mcp_client.is_connected:
        await mcp_client.disconnect()

    await db.close()

    logger.info("SIGMA IA shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SIGMA IA Trading Agent",
    description="Autonomous options trading agent powered by Claude + Alpaca MCP",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server and production deployments (Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(router)
