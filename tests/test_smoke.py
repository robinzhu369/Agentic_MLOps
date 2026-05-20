"""Smoke test: verify project structure and imports."""
from __future__ import annotations


def test_shared_lib_importable() -> None:
    """Verify shared_lib package can be imported."""
    import shared_lib
    assert shared_lib is not None


def test_config_loads() -> None:
    """Verify settings can be instantiated with defaults."""
    from shared_lib.config import get_settings

    settings = get_settings()
    assert settings.postgres.host == "localhost"
    assert settings.redis.url == "redis://localhost:6379/0"
    assert settings.qdrant.port == 6333


def test_logging_setup() -> None:
    """Verify structlog can be configured."""
    from shared_lib.logging import get_logger, setup_logging

    setup_logging(json_output=False)
    logger = get_logger("test")
    assert logger is not None
