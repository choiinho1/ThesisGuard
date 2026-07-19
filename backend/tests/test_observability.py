from __future__ import annotations

from types import SimpleNamespace

import pytest

from thesisguard_backend import observability


@pytest.mark.asyncio
async def test_alist_recent_traces_returns_empty_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        observability,
        "get_settings",
        lambda: SimpleNamespace(
            langfuse_enabled=False, langfuse_public_key=None, langfuse_secret_key=None
        ),
    )

    assert await observability.alist_recent_traces() == []


@pytest.mark.asyncio
async def test_alist_recent_traces_returns_empty_when_missing_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        observability,
        "get_settings",
        lambda: SimpleNamespace(
            langfuse_enabled=True, langfuse_public_key=None, langfuse_secret_key="sk-lf-x"
        ),
    )

    assert await observability.alist_recent_traces() == []
