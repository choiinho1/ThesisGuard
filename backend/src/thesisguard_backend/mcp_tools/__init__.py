"""MCP-style external data tools (B-owned).

Each module wraps one external data source in a small set of plain async
functions. None of these require a paid API key. ``agent_adapters.py``
calls into these modules and converts their output into
``thesisguard_agent.models.SourceDocument`` for the ResearchTools port that
C's LangGraph workflow consumes.
"""
