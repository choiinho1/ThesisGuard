"""Verify Langfuse credentials and send one small local connectivity trace."""

from __future__ import annotations

from thesisguard_backend.observability import (
    get_langfuse_client,
    langfuse_status,
    observe_llm_operation,
)


def main() -> int:
    status = langfuse_status()
    if status != "enabled":
        print(f"Langfuse is not ready: {status}")
        print("Set LANGFUSE_ENABLED=true and both project keys in backend/.env.")
        return 1

    client = get_langfuse_client()
    assert client is not None
    if not client.auth_check():
        print("Langfuse authentication failed. Check the project keys and base URL.")
        return 1

    with observe_llm_operation(
        "thesisguard.langfuse-connectivity-check",
        user_id="local-debug",
        session_id="local-setup",
        input={"check": "connectivity"},
        tags=["setup-check"],
    ) as trace:
        trace.set_output({"status": "ok"})
    client.flush()
    print("Langfuse authentication succeeded and a connectivity trace was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
