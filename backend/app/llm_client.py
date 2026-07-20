"""
Thin wrapper around the OpenAI API used by every LangGraph node that needs a
REAL LLM call (as opposed to the mock data in workflow/node_research.py).

Structured output is obtained via OpenAI Structured Outputs (`response_format`
with `type: json_schema` and `strict: True`), which guarantees the returned
JSON matches `tool_schema` exactly (every property required, no extras) -
this is the OpenAI equivalent of what forced tool-use gives you on Claude.

NOTE ON SCHEMAS: strict mode requires every object in the schema (top level
and nested) to set `"additionalProperties": false` and list every one of its
properties in `"required"`. The tool_schema dicts in each node_*.py file are
written with that in mind.
"""
import os
import json

from openai import OpenAI

_client: OpenAI | None = None

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def call_structured(
    system: str,
    user_content: str,
    tool_name: str,
    tool_schema: dict,
    max_tokens: int = 1500,
    model: str | None = None,
) -> dict:
    """Call the model and force it to respond with JSON matching `tool_schema`.

    Returns the parsed dict, matching `tool_schema`.
    """
    client = get_client()
    response = client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": tool_name,
                "strict": True,
                "schema": tool_schema,
            },
        },
    )

    choice = response.choices[0]
    if choice.message.content is None:
        raise RuntimeError(
            f"Model did not return content for '{tool_name}'. "
            f"finish_reason={choice.finish_reason}"
        )

    return json.loads(choice.message.content)
