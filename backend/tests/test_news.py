from __future__ import annotations

import pytest
from agents.models import ResearchRequest, StructuredThesis

from thesisguard_backend.agent_adapters import BackendResearchTools
from thesisguard_backend.mcp_tools import news
from thesisguard_backend.mcp_tools.news import NewsItem, _parse_items


def test_bing_rss_parser_keeps_competitor_detail_and_publisher_url() -> None:
    xml = """
    <rss xmlns:News="https://www.bing.com/news/search?q=test">
      <channel><item>
        <title>Why Robinhood stock is down today</title>
        <link>http://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fexample.com%2Fstory</link>
        <description>Meta Platforms is developing a competing prediction markets app.</description>
        <pubDate>Wed, 24 Jun 2026 08:36:13 GMT</pubDate>
        <News:Source>StockStory.org</News:Source>
      </item></channel>
    </rss>
    """

    items = _parse_items(xml, limit=5)

    assert len(items) == 1
    assert items[0].url == "https://example.com/story"
    assert "competing prediction markets app" in items[0].summary
    assert items[0].source == "StockStory.org"


@pytest.mark.asyncio
async def test_backend_news_search_covers_each_key_assumption(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_company_name(ticker: str) -> str:
        assert ticker == "HOOD"
        return "Robinhood Markets, Inc."

    async def fake_get_news(query: str, limit: int) -> list[NewsItem]:
        calls.append(query)
        return [
            NewsItem(
                title=f"Robinhood update {len(calls)}",
                url=f"https://example.com/{len(calls)}",
                published_at=None,
                source="Example",
                summary=f"Robinhood report for query {query}",
            )
        ][:limit]

    async def fake_fetch_news_text(url: str) -> str:
        assert url.startswith("https://example.com/")
        return (
            "Robinhood faces a new competitive signal. Meta Platforms is developing a "
            "competing prediction markets app. " + "Additional article context. " * 30
        )

    monkeypatch.setattr(
        "thesisguard_backend.agent_adapters.sec.get_company_name",
        fake_company_name,
    )
    monkeypatch.setattr(news, "get_news", fake_get_news)
    monkeypatch.setattr(
        "thesisguard_backend.agent_adapters._fetch_news_text",
        fake_fetch_news_text,
    )
    request = ResearchRequest(
        portfolio_id="portfolio-1",
        holding_id="holding-1",
        ticker="HOOD",
        thesis=StructuredThesis(
            raw_input="실적과 시장이 성장하고 경쟁자가 없다는 투자 논리입니다.",
            main_thesis="Robinhood의 장기 성장",
            key_assumptions=["실적 성장", "시장 성장", "경쟁자 없음"],
        ),
        round_no=1,
        candidate_limit=10,
    )

    documents = await BackendResearchTools().get_news(request)

    assert len(calls) == 4
    assert any("revenue earnings growth" in query for query in calls)
    assert any("market industry growth" in query for query in calls)
    assert any("competing app" in query for query in calls)
    assert len(documents) == 4
    assert all("Meta Platforms" in document.content for document in documents)
    assert all(document.metadata["full_article_fetched"] is True for document in documents)
