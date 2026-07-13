"""Sanity check for whichever LLM_PROVIDER/API key is set in backend/.env.

Makes exactly one real call: structures a sample investment thesis. Doesn't
touch the DB or any research tool, so it isolates "is my API key/model
config right" from "does the whole pipeline work" (see check_agent_compat.py
for the full pipeline check).

Run from backend/:
    PYTHONPATH="..;src" ../.venv/Scripts/python.exe scripts/check_llm_provider.py
"""

from __future__ import annotations

import asyncio

from agents.model import LangChainAnalysisModel

from thesisguard_backend.agent_adapters import create_chat_model
from thesisguard_backend.config import get_settings


async def main() -> None:
    settings = get_settings()
    print(f"LLM_PROVIDER={settings.llm_provider!r} LLM_MODEL={settings.llm_model!r}")

    chat_model = create_chat_model()
    model = LangChainAnalysisModel(chat_model)

    raw_input = (
        "NVDA is well positioned as Hyperscaler AI capex keeps growing and demand "
        "for its GPUs stays strong across data center customers."
    )
    result = await model.structure_thesis(raw_input)

    print("\nStructured thesis returned by the model:")
    print(f"  main_thesis: {result.main_thesis}")
    print(f"  key_assumptions: {result.key_assumptions}")
    print(f"  confidence_score: {result.confidence_score}, status: {result.status}")
    print(f"\nOK: {settings.llm_provider} responded and passed Pydantic validation.")


if __name__ == "__main__":
    asyncio.run(main())
