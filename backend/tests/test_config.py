import pytest

from app.config import PIPELINE_SETTINGS, MissingSettingsError, Settings, get_settings


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("NYT_API_KEY", "from-env")
    assert get_settings().nyt_api_key.get_secret_value() == "from-env"


def test_settings_load_from_dotenv_file(tmp_path):
    (tmp_path / ".env").write_text("PINATA_JWT=from-file\n")
    assert Settings().pinata_jwt.get_secret_value() == "from-file"


def test_require_lists_every_missing_variable():
    settings = Settings(_env_file=None, nyt_api_key="x", pinata_jwt="")
    with pytest.raises(MissingSettingsError) as exc:
        settings.require(*PIPELINE_SETTINGS)
    message = str(exc.value)
    assert "PINATA_JWT" in message  # empty string counts as missing
    assert "PRIVATE_KEY" in message
    assert "NYT_API_KEY" not in message


def test_require_passes_when_everything_is_set(settings):
    settings.require(*PIPELINE_SETTINGS)


def test_secrets_are_hidden_in_repr(settings):
    assert "nyt-test-key" not in repr(settings)
