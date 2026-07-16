from __future__ import annotations

from agents.alert_summary import (
    MAX_ALERT_SUMMARY_CHARS,
    AlertSummaryAgent,
    compact_alert_text,
)


class _Runnable:
    def __init__(self, result) -> None:
        self.result = result
        self.messages = None

    async def ainvoke(self, messages, config=None):
        self.messages = messages
        return self.result


class _ChatModel:
    def __init__(self, result) -> None:
        self.runnable = _Runnable(result)

    def with_structured_output(self, _schema):
        return self.runnable


async def test_alert_summary_agent_returns_one_line_under_200_characters() -> None:
    model = _ChatModel({"selected_indices": [0, 1]})
    agent = AlertSummaryAgent(model)

    result = await agent.summarize(
        ticker="MU",
        severity="MAJOR",
        content=(
            "MU 신뢰도가 40점에서 47점으로 상승했습니다. "
            f"HBM 장기 공급 계약이 핵심 근거이며 {'세부 근거 ' * 40}입니다."
        ),
    )

    assert len(result) <= MAX_ALERT_SUMMARY_CHARS
    assert result.endswith("…")
    assert "\n" not in result
    assert "<ticker>MU</ticker>" in str(model.runnable.messages[-1].content)
    assert "Do not rewrite" in str(model.runnable.messages[0].content)
    assert "신뢰도가 40점에서 47점" in result


async def test_alert_summary_agent_copies_selected_source_without_rewriting() -> None:
    model = _ChatModel({"selected_indices": [1]})
    agent = AlertSummaryAgent(model)

    result = await agent.summarize(
        ticker="MU",
        severity="MAJOR",
        content="신뢰도 변화가 있습니다. HBM 계약이 핵심 근거입니다.",
    )

    assert result == "MU: HBM 계약이 핵심 근거입니다."


def test_compact_alert_text_normalizes_whitespace_and_enforces_limit() -> None:
    result = compact_alert_text("  첫 문장\n\n두 번째 문장  ", max_chars=10)

    assert result == "첫 문장 두 번째…"
    assert len(result) <= 10
