"""
SILVERCAWN — Configuration via Pydantic Settings.

Reads from .env file. ALPACA_PAPER_TRADE is hardcoded to True as a safety guard.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Alpaca Paper Trading
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper_trade: bool = True  # Safety guard — always paper

    # NVIDIA AI (OpenAI-compatible endpoint)
    nvidia_api_key: Optional[str] = Field(None, alias="NVIDIA_API_KEY")
    nvidia_model: str = Field("", alias="NVIDIA_MODEL")
    nvidia_base_url: str = Field(
        "https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL"
    )

    # Autonomous mode
    autonomous_interval_seconds: int = 60

    # Database
    database_path: str = "silvercawn.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def validate_alpaca_keys(self) -> bool:
        """Check if Alpaca credentials are configured."""
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    def validate_nvidia_key(self) -> bool:
        """Check if NVIDIA AI API key is configured."""
        return bool(self.nvidia_api_key)


# Singleton instance
settings = Settings()
