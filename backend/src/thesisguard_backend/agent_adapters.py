"""Adapters that let C's ThesisGuardAgent run against B's DB and MCP tools.

C defines the ``ContextProvider`` / ``ResearchTools`` / ``AnalysisModel``
Protocols in ``agents.contracts`` and never calls a database or an external
API directly. B implements those Protocols here and injects them once at
application startup (see ``main.py``'s ``lifespan``).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from agents.contracts import EmbeddingModel
from agents.graph import ThesisGuardAgent
from agents.logic_graph import normalize_logic_graph
from agents.model import LangChainAnalysisModel
from agents.models import (
    AnalysisContext,
    EvidenceSourceType,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    StructuredThesis,
)
from agents.rag import HybridRAGRetriever
from agents.retrieval import (
    extract_relevant_passages,
    is_within_source_window,
    thesis_search_terms,
)
from agents.sanitization import sanitize_source_text
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings
from thesisguard_backend.evidence_history import refresh_evidence_history_file
from thesisguard_backend.mcp_tools import macro, market, news, sec

_MAX_FETCHED_DOCUMENT_CHARS = 120_000
_MAX_SELECTED_DOCUMENT_CHARS = 6000
_NEWS_ASSUMPTION_HINTS = (
    (("경쟁", "competitor", "competition", "rival", "entrant"), "competing app"),
    (("시장", "market", "industry", "tam"), "market industry growth"),
    (("실적", "매출", "이익", "revenue", "earnings", "profit"), "revenue earnings growth"),
)


def _assumption_news_query(
    *,
    company_name: str | None,
    ticker: str,
    assumption: str,
) -> str:
    normalized = assumption.casefold()
    company_keyword = (
        sanitize_source_text(company_name).split()[0].strip(",") if company_name else ticker
    )
    for stems, hint in _NEWS_ASSUMPTION_HINTS:
        if any(stem in normalized for stem in stems):
            return f"{company_keyword} {ticker} {hint}"
    return f'{company_keyword} {ticker} "{assumption}"'


def _structured_thesis_from_orm(thesis: orm.Thesis) -> StructuredThesis:
    score_breakdown = thesis.score_breakdown or None
    if score_breakdown and score_breakdown.get("scoring_method") != "EVIDENCE_NODE_MATRIX_V2":
        score_breakdown = None
    structured = StructuredThesis(
        raw_input=thesis.raw_input,
        main_thesis=thesis.main_thesis,
        key_assumptions=thesis.key_assumptions,
        positive_signals=thesis.positive_signals,
        negative_signals=thesis.negative_signals,
        key_risks=thesis.key_risks,
        logic_graph=thesis.logic_graph or None,
        score_breakdown=score_breakdown,
        confidence_score=thesis.confidence_score,
        status=thesis.status,
    )
    if structured.logic_graph is None:
        structured = structured.model_copy(
            update={
                "logic_graph": normalize_logic_graph(
                    None,
                    main_thesis=structured.main_thesis,
                    key_assumptions=structured.key_assumptions,
                )
            }
        )
    return structured


class BackendContextProvider:
    """Implements ``agents.contracts.ContextProvider``."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        history_dir: Path | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._history_dir = history_dir

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
            history = await refresh_evidence_history_file(
                session,
                holding=holding,
                thesis=holding.thesis,
                history_dir=self._history_dir,
            )

            return AnalysisContext(
                portfolio_id=portfolio_id,
                holding_id=holding_id,
                ticker=holding.ticker,
                thesis=_structured_thesis_from_orm(holding.thesis),
                portfolio_theses=portfolio_theses,
                evidence_history_summary=history.summary,
                evidence_history_document_ids=history.document_ids,
                evidence_history_source_urls=history.source_urls,
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
        records = await sec.get_filings(request.ticker, limit=9)
        collected_at = datetime.now(UTC)
        documents: list[SourceDocument] = []
        for record in records:
            if not is_within_source_window(
                record.filed_at,
                now=collected_at,
                lookback_days=request.lookback_days,
            ):
                continue
            content = await _fetch_text(record.url)
            if not content:
                continue
            selected_content = extract_relevant_passages(
                content,
                thesis_search_terms(request.thesis, request.focus_points),
                max_chars=_MAX_SELECTED_DOCUMENT_CHARS,
            )
            documents.append(
                SourceDocument(
                    document_id=record.accession_number,
                    source_type=EvidenceSourceType.SEC_FILING,
                    source_url=record.url,
                    title=record.title,
                    content=selected_content,
                    published_at=record.filed_at,
                    metadata={
                        "form": record.form,
                        "company_name": record.company_name or "",
                        "company_identity": (
                            record.company_identity.as_metadata()
                            if record.company_identity is not None
                            else {
                                "identifier_scheme": "SEC_CIK",
                                "identifier": record.cik or "",
                                "ticker": request.ticker.upper(),
                                "exchanges": [record.exchange] if record.exchange else [],
                                "legal_name": record.company_name or "",
                                "aliases": [],
                                "industry": "",
                                "official_domains": [],
                            }
                        ),
                        "original_chars": len(content),
                        "selected_chars": len(selected_content),
                    },
                )
            )
        return documents

    async def get_news(self, request: ResearchRequest) -> list[SourceDocument]:
        collected_at = datetime.now(UTC)
        company_identity = await sec.get_company_identity(request.ticker)
        company_name = company_identity.legal_name if company_identity else None
        company_query = f'"{company_name}" {request.ticker}' if company_name else request.ticker
        focus_terms = list(dict.fromkeys([*request.focus_points, *request.thesis.key_assumptions]))[
            :4
        ]
        queries = [
            company_query,
            *(
                _assumption_news_query(
                    company_name=company_name,
                    ticker=request.ticker,
                    assumption=term,
                )
                for term in focus_terms
            ),
        ]
        per_query_limit = max(3, (request.candidate_limit + len(queries) - 1) // len(queries))
        batches = await asyncio.gather(
            *(news.get_news(query, limit=per_query_limit) for query in queries)
        )

        candidates: list[tuple[str, news.NewsItem, str]] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        for query, items in zip(queries, batches, strict=True):
            for item in items:
                if not is_within_source_window(
                    item.published_at,
                    now=collected_at,
                    lookback_days=request.lookback_days,
                ):
                    continue
                title = sanitize_source_text(item.title)
                title_key = title.casefold()
                if item.url in seen_urls or title_key in seen_titles:
                    continue
                if not item.summary and not title:
                    continue
                seen_urls.add(item.url)
                seen_titles.add(title_key)
                candidates.append((query, item, title))
                if len(candidates) >= request.candidate_limit:
                    break
            if len(candidates) >= request.candidate_limit:
                break

        article_texts = await asyncio.gather(
            *(_fetch_news_text(item.url) for _, item, _ in candidates)
        )
        search_terms = thesis_search_terms(request.thesis, request.focus_points)
        documents: list[SourceDocument] = []
        for (query, item, title), article_text in zip(candidates, article_texts, strict=True):
            summary = sanitize_source_text(item.summary or title)
            content = (
                extract_relevant_passages(
                    article_text,
                    search_terms,
                    max_chars=_MAX_SELECTED_DOCUMENT_CHARS,
                )
                if article_text
                else summary
            )
            documents.append(
                SourceDocument(
                    document_id=item.url,
                    source_type=EvidenceSourceType.NEWS,
                    source_url=item.url,
                    title=title,
                    content=content,
                    published_at=item.published_at,
                    metadata={
                        "source": item.source,
                        "company_name": company_name or "",
                        "company_identity": (
                            company_identity.as_metadata()
                            if company_identity is not None
                            else {
                                "identifier_scheme": "TICKER",
                                "identifier": request.ticker.upper(),
                                "ticker": request.ticker.upper(),
                                "exchanges": [],
                                "legal_name": company_name or "",
                                "aliases": [company_name] if company_name else [],
                                "industry": "",
                                "official_domains": [],
                            }
                        ),
                        "search_query": query,
                        "full_article_fetched": bool(article_text),
                        "original_chars": len(article_text or summary),
                        "selected_chars": len(content),
                    },
                )
            )
        return documents

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
                    content=(
                        f"{label} ({point.series_id}) as of "
                        f"{point.as_of.isoformat()}: {point.value}"
                    ),
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
        lines = [" ".join(line.split()) for line in soup.get_text(separator="\n").splitlines()]
        text = "\n".join(line for line in lines if line)
        return text[:_MAX_FETCHED_DOCUMENT_CHARS]
    except Exception:  # noqa: BLE001 — a single filing fetch must not abort research
        return ""


async def _fetch_news_text(url: str) -> str:
    """Fetch readable publisher text; short/dynamic pages fall back to the RSS summary."""

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
            element.decompose()
        container = soup.find("article") or soup.find("main") or soup.body
        if container is None:
            return ""
        text = sanitize_source_text(container.get_text(separator=" "))
        return text[:_MAX_FETCHED_DOCUMENT_CHARS] if len(text) >= 400 else ""
    except Exception:  # noqa: BLE001 — a blocked publisher must not abort news research
        return ""


async def get_market_snapshot(ticker: str) -> market.MarketData:
    """Used by REST endpoints (dashboard) — not part of the ResearchTools contract."""

    return await market.get_market_data(ticker)


def create_chat_model(
    *,
    temperature: float | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
):
    """Builds the LangChain chat model selected via LLM_PROVIDER/LLM_MODEL.

    timeout + max_retries are set explicitly on every provider: without them,
    a rate-limited/quota-exhausted call (e.g. Gemini free-tier 429) doesn't
    fail fast — the client library's own backoff retries it for minutes,
    which the frontend just sees as a hung "Failed to fetch" with no error
    message. Better to fail in ~30-60s with a real exception the caller can
    surface.
    """

    settings = get_settings()
    temperature = 0 if temperature is None else temperature
    timeout = 30 if timeout is None else timeout
    max_retries = 1 if max_retries is None else max_retries
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
    if settings.llm_provider == "upstage":
        from langchain_upstage import ChatUpstage

        return ChatUpstage(
            model=settings.llm_model,
            upstage_api_key=settings.upstage_api_key,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
    raise ValueError(
        f"Unsupported LLM_PROVIDER={settings.llm_provider!r}. "
        "Add a branch here once the team picks another provider."
    )


def create_embedding_model() -> EmbeddingModel | None:
    """Build the configured RAG embedding client when its credentials are available."""

    settings = get_settings()
    if not settings.rag_enabled:
        return None
    provider = settings.rag_embedding_provider.strip().casefold()

    try:
        if provider == "openai":
            if not settings.openai_api_key:
                return None
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                model=settings.openai_embedding_model,
                api_key=settings.openai_api_key,
                timeout=settings.rag_embedding_timeout_seconds,
                max_retries=2,
            )
        if provider == "upstage":
            if not settings.upstage_api_key:
                return None
            from langchain_upstage import UpstageEmbeddings

            return UpstageEmbeddings(
                model=settings.upstage_embedding_model,
                api_key=settings.upstage_api_key,
                timeout=settings.rag_embedding_timeout_seconds,
                embed_batch_size=10,
            )
    except (ImportError, ValueError):
        return None

    raise ValueError(
        f"Unsupported RAG_EMBEDDING_PROVIDER={settings.rag_embedding_provider!r}. "
        "Use 'openai' or 'upstage'."
    )


def create_rag_retriever(
    *, dense_candidate_ratio: float | None = None
) -> HybridRAGRetriever | None:
    """Build provider-backed hybrid RAG, or retain deterministic retrieval."""

    embeddings = create_embedding_model()
    if embeddings is None:
        return None
    if dense_candidate_ratio is None:
        return HybridRAGRetriever(embeddings)
    return HybridRAGRetriever(embeddings, dense_candidate_ratio=dense_candidate_ratio)


def build_default_agent(session_factory: async_sessionmaker) -> ThesisGuardAgent:
    return ThesisGuardAgent(
        context_provider=BackendContextProvider(session_factory),
        research_tools=BackendResearchTools(),
        model=LangChainAnalysisModel(create_chat_model()),
        retriever=create_rag_retriever(),
    )


async def build_agent_from_settings(
    session_factory: async_sessionmaker, db: AsyncSession
) -> ThesisGuardAgent:
    """Like build_default_agent, but LLM/scoring/policy params come from AppSettings.

    Call this (and agents.graph.configure_agent(...) with the result) right
    before triggering an analysis run so admin-tuned parameters (see
    settings_service.py) take effect on the next run without a redeploy —
    the graph itself is otherwise compiled once at app startup.
    """

    from agents.runtime import WorkflowConfig

    from thesisguard_backend import settings_service

    snapshot = await settings_service.aget_settings_snapshot(db)
    config = WorkflowConfig(
        impact_weight_low=snapshot["scoring.impact_weight_low"],
        impact_weight_medium=snapshot["scoring.impact_weight_medium"],
        impact_weight_high=snapshot["scoring.impact_weight_high"],
        invalidation_streak_required=snapshot["scoring.invalidation_streak_required"],
        alert_major_movement_threshold=snapshot["policy.major_movement_threshold"],
    )
    model = create_chat_model(
        temperature=snapshot["llm.temperature"],
        timeout=snapshot["llm.timeout_seconds"],
        max_retries=snapshot["llm.max_retries"],
    )
    return ThesisGuardAgent(
        context_provider=BackendContextProvider(session_factory),
        research_tools=BackendResearchTools(),
        model=LangChainAnalysisModel(model),
        retriever=create_rag_retriever(dense_candidate_ratio=snapshot["rag.dense_candidate_ratio"]),
        config=config,
    )
