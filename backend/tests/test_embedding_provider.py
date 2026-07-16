from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from thesisguard_backend import agent_adapters


def _settings(**overrides):
    values = {
        "rag_enabled": True,
        "rag_embedding_provider": "openai",
        "openai_api_key": "test-openai-key",
        "openai_embedding_model": "text-embedding-3-small",
        "upstage_api_key": "test-upstage-key",
        "upstage_embedding_model": "solar-embedding-1-large",
        "rag_embedding_timeout_seconds": 20,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_create_openai_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(OpenAIEmbeddings=FakeOpenAIEmbeddings),
    )
    monkeypatch.setattr(agent_adapters, "get_settings", _settings)

    result = agent_adapters.create_embedding_model()

    assert isinstance(result, FakeOpenAIEmbeddings)
    assert captured == {
        "model": "text-embedding-3-small",
        "api_key": "test-openai-key",
        "timeout": 20,
        "max_retries": 2,
    }


def test_create_upstage_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeUpstageEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_upstage",
        SimpleNamespace(UpstageEmbeddings=FakeUpstageEmbeddings),
    )
    monkeypatch.setattr(
        agent_adapters,
        "get_settings",
        lambda: _settings(rag_embedding_provider="upstage"),
    )

    result = agent_adapters.create_embedding_model()

    assert isinstance(result, FakeUpstageEmbeddings)
    assert captured == {
        "model": "solar-embedding-1-large",
        "api_key": "test-upstage-key",
        "timeout": 20,
        "embed_batch_size": 10,
    }


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"rag_enabled": False},
        {"openai_api_key": None},
        {"rag_embedding_provider": "upstage", "upstage_api_key": None},
    ],
)
def test_embedding_model_is_unavailable_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict,
) -> None:
    monkeypatch.setattr(agent_adapters, "get_settings", lambda: _settings(**overrides))

    assert agent_adapters.create_embedding_model() is None


def test_unknown_embedding_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_adapters,
        "get_settings",
        lambda: _settings(rag_embedding_provider="unknown"),
    )

    with pytest.raises(ValueError, match="Unsupported RAG_EMBEDDING_PROVIDER"):
        agent_adapters.create_embedding_model()
