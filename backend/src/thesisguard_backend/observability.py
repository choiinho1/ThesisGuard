"""Optional Langfuse tracing for ThesisGuard's LLM workflows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from thesisguard_backend.config import get_settings


@dataclass(slots=True)
class LLMTrace:
    """The request-local callback config and root Langfuse observation."""

    runnable_config: RunnableConfig | None = None
    _observation: Any | None = None

    def set_output(self, output: Any) -> None:
        """Set explicit root observation and trace output for later debugging."""

        if self._observation is None:
            return
        self._observation.update(output=output)


@lru_cache
def _build_langfuse_client(
    enabled: bool,
    public_key: str | None,
    secret_key: str | None,
    base_url: str,
    environment: str,
    sample_rate: float,
    debug: bool,
) -> Langfuse | None:
    if not enabled or not public_key or not secret_key:
        return None
    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        environment=environment,
        sample_rate=sample_rate,
        debug=debug,
    )


def get_langfuse_client() -> Langfuse | None:
    """Return the configured client, or ``None`` when tracing is disabled."""

    settings = get_settings()
    return _build_langfuse_client(
        settings.langfuse_enabled,
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        settings.langfuse_base_url,
        settings.langfuse_tracing_environment,
        settings.langfuse_sample_rate,
        settings.langfuse_debug,
    )


def langfuse_status() -> str:
    """Return a secret-free status suitable for startup/health diagnostics."""

    settings = get_settings()
    if not settings.langfuse_enabled:
        return "disabled"
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return "missing_credentials"
    return "enabled"


@contextmanager
def observe_llm_operation(
    name: str,
    *,
    user_id: str,
    session_id: str,
    input: Any,
    metadata: Mapping[str, Any] | None = None,
    tags: Sequence[str] = (),
) -> Iterator[LLMTrace]:
    """Create one agent trace containing LangGraph/LangChain child spans."""

    client = get_langfuse_client()
    settings = get_settings()
    if client is None:
        yield LLMTrace()
        return

    propagated_metadata = {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        **{key: str(value)[:200] for key, value in (metadata or {}).items() if value is not None},
    }
    trace_tags = ["thesisguard", *tags]

    with propagate_attributes(
        trace_name=name,
        user_id=user_id,
        session_id=session_id,
        tags=trace_tags,
        metadata=propagated_metadata,
    ):
        with client.start_as_current_observation(
            name=name,
            as_type="agent",
            input=input,
            metadata=propagated_metadata,
        ) as observation:
            handler = CallbackHandler(public_key=settings.langfuse_public_key)
            runnable_config: RunnableConfig = {
                "callbacks": [handler],
                "run_name": name,
                "metadata": propagated_metadata,
            }
            yield LLMTrace(runnable_config=runnable_config, _observation=observation)


@dataclass(slots=True)
class LangfuseTraceSummary:
    """One row of Langfuse's ``GET /api/public/traces`` response, trimmed to
    what the admin console table shows — full trace detail (span tree,
    prompts) still requires clicking through to Langfuse itself."""

    id: str
    name: str | None
    timestamp: str | None
    user_id: str | None
    latency_seconds: float | None
    total_cost: float | None
    tags: list[str]


async def alist_recent_traces(*, limit: int = 20) -> list[LangfuseTraceSummary]:
    """Fetch the most recent traces via Langfuse's Public API.

    Returns an empty list when tracing isn't configured — mirrors
    ``langfuse_status()`` rather than raising, so a disabled/unconfigured
    project just shows an empty table instead of an error banner.
    """

    settings = get_settings()
    if (
        not settings.langfuse_enabled
        or not settings.langfuse_public_key
        or not settings.langfuse_secret_key
    ):
        return []

    async with httpx.AsyncClient(
        base_url=settings.langfuse_base_url,
        auth=(settings.langfuse_public_key, settings.langfuse_secret_key),
        timeout=10,
    ) as client:
        response = await client.get(
            "/api/public/traces",
            params={"limit": limit, "orderBy": "timestamp.desc"},
        )
        response.raise_for_status()
        payload = response.json()

    return [
        LangfuseTraceSummary(
            id=item["id"],
            name=item.get("name"),
            timestamp=item.get("timestamp"),
            user_id=item.get("userId"),
            latency_seconds=item.get("latency"),
            total_cost=item.get("totalCost"),
            tags=item.get("tags") or [],
        )
        for item in payload.get("data", [])
    ]


def shutdown_langfuse() -> None:
    """Flush buffered traces during FastAPI shutdown."""

    client = get_langfuse_client()
    if client is not None:
        client.shutdown()
