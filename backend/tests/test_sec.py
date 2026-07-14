from datetime import datetime

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
