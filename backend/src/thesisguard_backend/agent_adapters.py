"""Adapters that let C's ThesisGuardAgent run against B's DB and MCP tools.

C defines the ``ContextProvider`` / ``ResearchTools`` / ``AnalysisModel``
Protocols in ``agents.contracts`` and never calls a database or an external
API directly. B implements those Protocols here and injects them once at
application startup (see ``main.py``'s ``lifespan``).
"""

from __future__ import annotations

import uuid

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from agents.graph import ThesisGuardAgent
from agents.model import LangChainAnalysisModel
from agents.models import (
    AnalysisContext,
    EvidenceSourceType,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    StructuredThesis,
)
from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings
from thesisguard_backend.mcp_tools import macro, market, news, sec

_MAX_DOCUMENT_CHARS = 8000


def _structured_thesis_from_orm(thesis: orm.Thesis) -> StructuredThesis:
    return StructuredThesis(
        raw_input=thesis.raw_input,
        main_thesis=thesis.main_thesis,
        key_assumptions=thesis.key_assumptions,
        positive_signals=thesis.positive_signals,
        negative_signals=thesis.negative_signals,
        key_risks=thesis.key_risks,
        confidence_score=thesis.confidence_score,
        status=thesis.status,
    )


class BackendContextProvider:
    """Implements ``agents.contracts.ContextProvider``."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def load_analysis_context(self, portfolio_id: str, holding_id: str) -> AnalysisContext:
        async with self._session_factory() as session:
            holding = await session.scalar(
                select(orm.Holding)
                .where(orm.Holding.id == uuid.UUID(holding_id))
                .options(selectinload(orm.Holding.thesis))
            )
            if holding is None or str(holding.portfolio_id) != portfolio_id:
                raise ValueError(f"Holding {holding_id} not found in portfolio {portfolio_id}")
            if holding.thesis is None:
                raise ValueError(f"Holding {holding_id} has no registered thesis yet")

            portfolio_theses = await self._load_portfolio_theses(session, portfolio_id)

            return AnalysisContext(
                portfolio_id=portfolio_id,
                holding_id=holding_id,
                ticker=holding.ticker,
                thesis=_structured_thesis_from_orm(holding.thesis),
                portfolio_theses=portfolio_theses,
            )

    async def load_portfolio_theses(self, portfolio_id: str) -> list[PortfolioThesis]:
        async with self._session_factory() as session:
            return await self._load_portfolio_theses(session, portfolio_id)

    @staticmethod
    async def _load_portfolio_theses(session, portfolio_id: str) -> list[PortfolioThesis]:
        portfolio_holdings = await session.scalars(
            select(orm.Holding)
            .where(orm.Holding.portfolio_id == uuid.UUID(portfolio_id))
            .options(selectinload(orm.Holding.thesis))
        )
        return [
            PortfolioThesis(
                holding_id=str(item.id),
                ticker=item.ticker,
                current_weight=item.current_weight,
                thesis=_structured_thesis_from_orm(item.thesis),
            )
            for item in portfolio_holdings
            if item.thesis is not None
        ]


class BackendResearchTools:
    """Implements ``agents.contracts.ResearchTools`` using the MCP tool modules."""

    async def get_filings(self, request: ResearchRequest) -> list[SourceDocument]:
        records = await sec.get_filings(request.ticker, limit=3)
        documents: list[SourceDocument] = []
        for record in records:
            content = await _fetch_text(record.url)
            if not content:
                continue
            documents.append(
                SourceDocument(
                    document_id=record.accession_number,
                    source_type=EvidenceSourceType.SEC_FILING,
                    source_url=record.url,
                    title=record.title,
                    content=content,
                    published_at=record.filed_at,
                    metadata={"form": record.form},
                )
            )
        return documents

    async def get_news(self, request: ResearchRequest) -> list[SourceDocument]:
        query = request.ticker
        if request.focus_points:
            query = f"{request.ticker} {request.focus_points[0]}"
        items = await news.get_news(query, limit=5)
        return [
            SourceDocument(
                document_id=item.url,
                source_type=EvidenceSourceType.NEWS,
                source_url=item.url,
                title=item.title,
                content=item.summary or item.title,
                published_at=item.published_at,
                metadata={"source": item.source},
            )
            for item in items
            if item.summary or item.title
        ]

    async def get_macro(self, request: ResearchRequest) -> list[SourceDocument]:
        points = {
            "interest_rate": await macro.get_interest_rate(),
            "treasury_yield": await macro.get_treasury_yield(),
            "cpi": await macro.get_cpi(),
        }
        documents: list[SourceDocument] = []
        for label, point in points.items():
            if point is None:
                continue
            documents.append(
                SourceDocument(
                    document_id=f"{point.series_id}:{point.as_of.isoformat()}",
                    source_type=EvidenceSourceType.MACRO,
                    source_url=f"https://fred.stlouisfed.org/series/{point.series_id}",
                    title=f"FRED {point.series_id} ({label})",
                    content=f"{label} ({point.series_id}) as of {point.as_of.isoformat()}: {point.value}",
                    published_at=None,
                    metadata={"label": label, "value": point.value},
                )
            )
        return documents


async def _fetch_text(url: str) -> str:
    """Download a filing document and strip it down to plain text."""

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": get_settings().sec_user_agent})
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:_MAX_DOCUMENT_CHARS]
    except Exception:  # noqa: BLE001 — a single filing fetch must not abort research
        return ""


async def get_market_snapshot(ticker: str) -> market.MarketData:
    """Used by REST endpoints (dashboard) — not part of the ResearchTools contract."""

    return await market.get_market_data(ticker)


def create_chat_model():
    """Builds the LangChain chat model selected via LLM_PROVIDER/LLM_MODEL."""

    settings = get_settings()
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0)
    raise ValueError(
        f"Unsupported LLM_PROVIDER={settings.llm_provider!r}. "
        "Add a branch here once the team picks another provider."
    )


def build_default_agent(session_factory: async_sessionmaker) -> ThesisGuardAgent:
    return ThesisGuardAgent(
        context_provider=BackendContextProvider(session_factory),
        research_tools=BackendResearchTools(),
        model=LangChainAnalysisModel(create_chat_model()),
    )
