"""Request-local LangChain configuration for direct model calls.

LangGraph automatically propagates its ``RunnableConfig`` to nested model
calls. Direct agent entry points (thesis structuring and portfolio Q&A) do not
have a graph around them, so they use this context variable to pass callbacks
without coupling the provider-neutral agent package to an observability SDK.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from langchain_core.runnables import RunnableConfig

_runnable_config: ContextVar[RunnableConfig | None] = ContextVar(
    "thesisguard_model_runnable_config", default=None
)


def get_model_runnable_config() -> RunnableConfig | None:
    """Return the callbacks/metadata for the current direct model call."""

    return _runnable_config.get()


@contextmanager
def use_model_runnable_config(config: RunnableConfig | None) -> Iterator[None]:
    """Temporarily bind a LangChain config to the current async request."""

    token = _runnable_config.set(config)
    try:
        yield
    finally:
        _runnable_config.reset(token)
