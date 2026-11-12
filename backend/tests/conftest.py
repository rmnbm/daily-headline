import base64
import io
import socket

import pytest
from PIL import Image

from app.config import Settings, get_settings

# Anvil/Hardhat's first default dev key: public, holds no real funds.
TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_CONTRACT = "0x80D111626caD7588Fd514324911f08bfa53FE71C"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Isolate every test from the developer's machine.

    - Run in a temporary directory, so a real `.env` is never loaded.
    - Clear environment variables that map to settings.
    - Block network sockets: any real HTTP or RPC call fails loudly.
    """
    monkeypatch.chdir(tmp_path)
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    get_settings.cache_clear()

    def no_network(*args, **kwargs):
        raise RuntimeError("Network access is disabled during tests")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        nyt_api_key="nyt-test-key",
        cf_account_id="cf-account",
        cf_api_token="cf-token",
        pinata_jwt="pinata-jwt",
        rpc_url="http://rpc.invalid",
        private_key=TEST_PRIVATE_KEY,
        contract_address=TEST_CONTRACT,
        api_key="test-api-key",
        database_path=tmp_path / "test.db",
    )


def make_jpeg_b64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
