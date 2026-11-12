"""Application settings, read from environment variables or a `.env` file."""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingSettingsError(RuntimeError):
    """Raised when a setting needed by the requested operation is not configured."""


class Settings(BaseSettings):
    """All configuration in one place.

    Secrets are optional at load time so the code can be imported and tested
    without any key. Each operation calls `require()` for what it actually
    needs, which gives a clear error listing the missing variables.
    `SecretStr` keeps secrets out of logs and reprs.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # External services used by the pipeline
    nyt_api_key: SecretStr | None = None
    cf_account_id: str | None = None
    cf_api_token: SecretStr | None = None
    pinata_jwt: SecretStr | None = None
    rpc_url: SecretStr | None = None  # often embeds the provider's API key
    private_key: SecretStr | None = None
    contract_address: str | None = None

    # API
    api_key: SecretStr | None = None
    database_path: Path = Path("data/daily_headline.db")
    log_level: str = "INFO"

    def missing(self, *names: str) -> list[str]:
        """Return the environment variable names of the unset settings among `names`."""
        missing = []
        for name in names:
            value = getattr(self, name)
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if not value:
                missing.append(name.upper())
        return missing

    def require(self, *names: str) -> None:
        if missing := self.missing(*names):
            raise MissingSettingsError(f"Missing required settings: {', '.join(missing)}")


PIPELINE_SETTINGS = (
    "nyt_api_key",
    "cf_account_id",
    "cf_api_token",
    "pinata_jwt",
    "rpc_url",
    "private_key",
    "contract_address",
)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
