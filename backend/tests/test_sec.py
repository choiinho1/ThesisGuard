from datetime import UTC, datetime, timedelta

import pytest
from agents.models import ResearchRequest, StructuredThesis

from thesisguard_backend.agent_adapters import BackendResearchTools
from thesisguard_backend.mcp_tools.sec import FilingRecord, _prioritize_filings


def _filing(accession: str, form: str, day: int) -> FilingRecord:
    return FilingRecord(
        accession_number=accession,
        form=form,
        filed_at=datetime(2026, 7, day),
        title=f"Example {form}",
        url=f"https://www.sec.gov/{accession}",
    )


def test_prioritize_filings_keeps_periodic_reports_ahead_of_extra_8k_items() -> None:
    records = [
        _filing("8k-new", "8-K", 14),
        _filing("8k-old", "8-K", 13),
        _filing("10q", "10-Q", 12),
        _filing("10k", "10-K", 11),
    ]

    selected = _prioritize_filings(records, limit=3)

    assert [item.form for item in selected] == ["10-Q", "10-K", "8-K"]
    assert selected[-1].accession_number == "8k-new"


def test_prioritize_filings_respects_zero_limit() -> None:
    assert _prioritize_filings([_filing("10q", "10-Q", 12)], limit=0) == []


@pytest.mark.asyncio
async def test_backend_filings_discards_out_of_window_items_before_fetch(monkeypatch) -> None:
    now = datetime.now(UTC)
    fetched_urls: list[str] = []
    records = [
        FilingRecord(
            accession_number="recent",
            form="8-K",
            filed_at=now - timedelta(days=2),
            title="Recent filing",
            url="https://www.sec.gov/recent",
        ),
        FilingRecord(
            accession_number="stale",
            form="10-Q",
            filed_at=now - timedelta(days=31),
            title="Stale filing",
            url="https://www.sec.gov/stale",
        ),
        FilingRecord(
            accession_number="future",
            form="8-K",
            filed_at=now + timedelta(days=1),
            title="Future filing",
            url="https://www.sec.gov/future",
        ),
    ]

    async def fake_get_filings(ticker: str, limit: int) -> list[FilingRecord]:
        assert ticker == "NVDA"
        return records[:limit]

    async def fake_fetch_text(url: str) -> str:
        fetched_urls.append(url)
        return "NVDA AI infrastructure demand and revenue growth. " * 20

    monkeypatch.setattr(
        "thesisguard_backend.agent_adapters.sec.get_filings",
        fake_get_filings,
    )
    monkeypatch.setattr(
        "thesisguard_backend.agent_adapters._fetch_text",
        fake_fetch_text,
    )
    request = ResearchRequest(
        portfolio_id="portfolio-1",
        holding_id="holding-1",
        ticker="NVDA",
        thesis=StructuredThesis(
            raw_input="AI 인프라 수요가 계속 성장한다는 투자 논리입니다.",
            main_thesis="AI 인프라 수요 성장",
            key_assumptions=["AI 인프라 수요가 성장한다"],
        ),
        round_no=1,
    )

    documents = await BackendResearchTools().get_filings(request)

    assert [item.document_id for item in documents] == ["recent"]
    assert fetched_urls == ["https://www.sec.gov/recent"]
