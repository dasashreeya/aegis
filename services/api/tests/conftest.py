"""Test isolation from the developer's own configuration.

A working ``.env`` at the repository root points at a real Google project. That
is exactly what you want when running the demo and exactly what you do not want
when running the suite: the tests would spend money and fail offline. So every
test that is not marked ``live`` runs in ``mock`` mode regardless of what the
environment says, and the settings caches are cleared around each test so the
two never bleed into each other.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.dependencies import get_orchestrator


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Live tests spend money, so they never run by accident.

    Gating on the marker expression rather than on pytest configuration means
    this holds from any working directory: `pytest` anywhere skips them,
    `pytest -m live` runs them.
    """
    if "live" in (config.option.markexpr or ""):
        return
    skip_live = pytest.mark.skip(reason="live tests hit real Vertex AI; run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_orchestrator.cache_clear()


@pytest.fixture(autouse=True)
def isolated_settings(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if "live" not in request.keywords:
        # Environment variables win over .env in pydantic-settings, so this
        # pins the mode without editing anyone's local configuration.
        monkeypatch.setenv("AEGIS_MODE", "mock")
        monkeypatch.setenv("AEGIS_STORAGE_BACKEND", "memory")
        monkeypatch.setenv("AEGIS_TRACE_EXPORTER", "none")
    _clear_caches()
    yield
    _clear_caches()
