"""LangGraph workflow for continuous investment-thesis verification."""

from __future__ import annotations

import asyncio
import operator
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict, TypeVar

from langgraph.graph import END, START, StateGraph

from thesisguard_agent.models import (
    AlertDecision,
    AnalysisContext,
    DebateReport,
    EvidenceAssessment,
    EvidenceClassification,
    EvidenceItem,
    JudgeDecision,
    PortfolioAnalysis,
    PortfolioThesis,
    ResearchRequest,
    SourceDocument,
    StructuredThesis,
    ThesisAnalysisResult,
    ThesisStatus,
)
from thesisguard_agent.policy import decide_alert
from thesisguard_agent.ports import AnalysisModel, ContextProvider, ResearchTools

ModelResult = TypeVar("ModelResult")


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    max_research_rounds: int = 2
    min_grounded_evidence: int = 2
    model_max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_research_rounds < 1:
            raise ValueError("max_research_rounds must be at least 1")
        if self.min_grounded_evidence < 1:
            raise ValueError("min_grounded_evidence must be at least 1")
        if self.model_max_attempts < 1:
            raise ValueError("model_max_attempts must be at least 1")


class AnalysisState(TypedDict, total=False):
    portfolio_id: str
    holding_id: str
    ticker: str
    thesis_snapshot: StructuredThesis
    portfolio_theses: list[PortfolioThesis]
    research_round: int
    focus_points: list[str]
    research_data: Annotated[list[SourceDocument], operator.add]
    source_errors: Annotated[list[str], operator.add]
    evidence_list: list[EvidenceItem]
    needs_more_research: bool
    bull_report: DebateReport
    bear_report: DebateReport
    judge_decision: JudgeDecision
    portfolio_analysis: PortfolioAnalysis
    alert_decision: AlertDecision
    result: ThesisAnalysisResult


class ThesisGuardAgent:
    """AI-owned service. Backend injects context and MCP-backed research ports."""

    def __init__(
        self,
        *,
        context_provider: ContextProvider,
        research_tools: ResearchTools,
        model: AnalysisModel,
        config: WorkflowConfig | None = None,
    ) -> None:
        self._context_provider = context_provider
        self._research_tools = research_tools
        self._model = model
        self._config = config or WorkflowConfig()
        self.graph = self._build_graph()

    async def structure_thesis(self, raw_input: str) -> StructuredThesis:
        return await self._call_model(self._model.structure_thesis, raw_input)

    async def _call_model(
        self, method: Callable[..., Awaitable[ModelResult]], *args: object
    ) -> ModelResult:
        error: Exception | None = None
        for _ in range(self._config.model_max_attempts):
            try:
                return await method(*args)
            except Exception as exc:
                error = exc
        assert error is not None
        raise error

    async def run_analysis_workflow(
        self, portfolio_id: str, holding_id: str
    ) -> ThesisAnalysisResult:
        final_state = await self.graph.ainvoke(
            {
                "portfolio_id": portfolio_id,
                "holding_id": holding_id,
                "research_round": 0,
                "focus_points": [],
                "research_data": [],
                "source_errors": [],
            },
            config={"recursion_limit": 30},
        )
        return final_state["result"]

    def _build_graph(self):
        graph = StateGraph(AnalysisState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("prepare_research", self._prepare_research)
        graph.add_node("filing_research", self._filing_research)
        graph.add_node("news_research", self._news_research)
        graph.add_node("macro_research", self._macro_research)
        graph.add_node("classify_evidence", self._classify_evidence)
        graph.add_node("debate_start", self._debate_start)
        graph.add_node("bull_agent", self._bull_agent)
        graph.add_node("bear_agent", self._bear_agent)
        graph.add_node("judge_agent", self._judge_agent)
        graph.add_node("portfolio_agent", self._portfolio_agent)
        graph.add_node("alert_decision", self._alert_decision)
        graph.add_node("finalize", self._finalize)

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "prepare_research")
        graph.add_edge("prepare_research", "filing_research")
        graph.add_edge("prepare_research", "news_research")
        graph.add_edge("prepare_research", "macro_research")
        graph.add_edge(
            ["filing_research", "news_research", "macro_research"], "classify_evidence"
        )
        graph.add_conditional_edges(
            "classify_evidence",
            self._route_after_classification,
            {"retry": "prepare_research", "debate": "debate_start"},
        )
        graph.add_edge("debate_start", "bull_agent")
        graph.add_edge("debate_start", "bear_agent")
        graph.add_edge(["bull_agent", "bear_agent"], "judge_agent")
        graph.add_edge("judge_agent", "portfolio_agent")
        graph.add_edge("portfolio_agent", "alert_decision")
        graph.add_edge("alert_decision", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    async def _load_context(self, state: AnalysisState) -> dict:
        context: AnalysisContext = await self._context_provider.load_analysis_context(
            state["portfolio_id"], state["holding_id"]
        )
        identifiers_match = (
            context.portfolio_id == state["portfolio_id"]
            and context.holding_id == state["holding_id"]
        )
        if not identifiers_match:
            raise ValueError(
                "Context provider returned identifiers for a different analysis request"
            )
        return {
            "ticker": context.ticker,
            "thesis_snapshot": context.thesis,
            "portfolio_theses": context.portfolio_theses,
        }

    async def _prepare_research(self, state: AnalysisState) -> dict:
        return {"research_round": state["research_round"] + 1}

    def _research_request(self, state: AnalysisState) -> ResearchRequest:
        return ResearchRequest(
            portfolio_id=state["portfolio_id"],
            holding_id=state["holding_id"],
            ticker=state["ticker"],
            thesis=state["thesis_snapshot"],
            round_no=state["research_round"],
            focus_points=state.get("focus_points", []),
        )

    async def _run_research(self, state: AnalysisState, source: str) -> dict:
        request = self._research_request(state)
        method = getattr(self._research_tools, source)
        try:
            documents = await method(request)
            return {"research_data": documents}
        except Exception as exc:  # A source failure must not stop the remaining sources.
            return {"source_errors": [f"{source}: {type(exc).__name__}: {exc}"]}

    async def _filing_research(self, state: AnalysisState) -> dict:
        return await self._run_research(state, "get_filings")

    async def _news_research(self, state: AnalysisState) -> dict:
        return await self._run_research(state, "get_news")

    async def _macro_research(self, state: AnalysisState) -> dict:
        return await self._run_research(state, "get_macro")

    async def _classify_evidence(self, state: AnalysisState) -> dict:
        unique_documents: dict[str, SourceDocument] = {}
        for document in state.get("research_data", []):
            unique_documents.setdefault(document.document_id, document)

        async def classify(document: SourceDocument) -> EvidenceItem:
            try:
                assessment = await self._call_model(
                    self._model.classify_evidence, state["thesis_snapshot"], document
                )
            except Exception as exc:
                assessment = EvidenceAssessment(
                    classification=EvidenceClassification.UNCERTAIN,
                    impact=0,
                    reason=f"분류 모델 오류({type(exc).__name__})로 불확실 처리했습니다.",
                    related_assumptions=state["thesis_snapshot"].key_assumptions,
                    content_snippet=document.content[:500],
                )
            return EvidenceItem(
                document_id=document.document_id,
                source_type=document.source_type,
                source_url=document.source_url,
                content_snippet=assessment.content_snippet,
                classification=assessment.classification,
                impact=assessment.impact,
                reason=assessment.reason,
                related_assumptions=assessment.related_assumptions,
                published_at=document.published_at,
            )

        evidence = await asyncio.gather(*(classify(doc) for doc in unique_documents.values()))
        grounded = [
            item
            for item in evidence
            if item.classification
            in {EvidenceClassification.SUPPORT, EvidenceClassification.CONTRADICT}
        ]
        needs_more = len(grounded) < self._config.min_grounded_evidence
        focus_points = list(
            dict.fromkeys(
                assumption
                for item in evidence
                if item.classification == EvidenceClassification.UNCERTAIN
                for assumption in item.related_assumptions
            )
        )
        if not focus_points and needs_more:
            focus_points = state["thesis_snapshot"].key_assumptions
        return {
            "evidence_list": evidence,
            "needs_more_research": needs_more,
            "focus_points": focus_points,
        }

    def _route_after_classification(self, state: AnalysisState) -> Literal["retry", "debate"]:
        if (
            state["needs_more_research"]
            and state["research_round"] < self._config.max_research_rounds
        ):
            return "retry"
        return "debate"

    async def _debate_start(self, state: AnalysisState) -> dict:
        return {}

    async def _bull_agent(self, state: AnalysisState) -> dict:
        try:
            report = await self._call_model(
                self._model.build_bull_report,
                state["thesis_snapshot"],
                state["evidence_list"],
            )
        except Exception:
            report = DebateReport(summary="Bull Agent 응답 실패로 지지 판단을 보류했습니다.")
        return {"bull_report": report}

    async def _bear_agent(self, state: AnalysisState) -> dict:
        try:
            report = await self._call_model(
                self._model.build_bear_report,
                state["thesis_snapshot"],
                state["evidence_list"],
            )
        except Exception:
            report = DebateReport(summary="Bear Agent 응답 실패로 반박 판단을 보류했습니다.")
        return {"bear_report": report}

    async def _judge_agent(self, state: AnalysisState) -> dict:
        directional = [
            item
            for item in state["evidence_list"]
            if item.classification
            in {EvidenceClassification.SUPPORT, EvidenceClassification.CONTRADICT}
        ]
        if not directional:
            thesis = state["thesis_snapshot"]
            return {
                "judge_decision": JudgeDecision(
                    updated_confidence=thesis.confidence_score,
                    updated_status=ThesisStatus.UNCHANGED,
                    change_reason="검증 가능한 방향성 근거가 없어 기존 Thesis를 유지합니다.",
                    judge_summary="신규 근거가 부족하여 판단을 보류했습니다.",
                    observation_points=state.get("focus_points", []),
                )
            }
        try:
            decision = await self._call_model(
                self._model.judge,
                state["thesis_snapshot"],
                state["evidence_list"],
                state["bull_report"],
                state["bear_report"],
            )
        except Exception:
            thesis = state["thesis_snapshot"]
            decision = JudgeDecision(
                updated_confidence=thesis.confidence_score,
                updated_status=ThesisStatus.UNCHANGED,
                change_reason="Judge Agent 재시도 실패로 기존 Thesis를 유지합니다.",
                judge_summary="판정 모델 응답을 검증할 수 없어 판단을 보류했습니다.",
                observation_points=state.get("focus_points", []),
            )
        return {"judge_decision": decision}

    async def _portfolio_agent(self, state: AnalysisState) -> dict:
        decision = state["judge_decision"]
        updated_thesis = state["thesis_snapshot"].model_copy(
            update={
                "confidence_score": decision.updated_confidence,
                "status": decision.updated_status,
            }
        )
        portfolio = []
        found_current = False
        for item in state.get("portfolio_theses", []):
            if item.holding_id == state["holding_id"]:
                portfolio.append(item.model_copy(update={"thesis": updated_thesis}))
                found_current = True
            else:
                portfolio.append(item)
        if not found_current:
            portfolio.append(
                PortfolioThesis(
                    holding_id=state["holding_id"],
                    ticker=state["ticker"],
                    thesis=updated_thesis,
                )
            )
        try:
            analysis = await self._call_model(
                self._model.analyze_concentration, portfolio
            )
        except Exception:
            analysis = PortfolioAnalysis(summary="집중도 분석 모델 응답을 확인할 수 없습니다.")
        return {"portfolio_analysis": analysis}

    async def _alert_decision(self, state: AnalysisState) -> dict:
        alert = decide_alert(
            state["thesis_snapshot"].status, state["judge_decision"].updated_status
        )
        return {"alert_decision": alert}

    async def _finalize(self, state: AnalysisState) -> dict:
        decision = state["judge_decision"]
        result = ThesisAnalysisResult(
            portfolio_id=state["portfolio_id"],
            holding_id=state["holding_id"],
            ticker=state["ticker"],
            evidence=state["evidence_list"],
            bull_summary=state["bull_report"].summary,
            bear_summary=state["bear_report"].summary,
            judge_summary=decision.judge_summary,
            updated_confidence=decision.updated_confidence,
            updated_status=decision.updated_status,
            change_reason=decision.change_reason,
            conflicting_assumptions=decision.conflicting_assumptions,
            observation_points=decision.observation_points,
            concentration=state["portfolio_analysis"],
            alert_decision=state["alert_decision"],
            research_rounds=state["research_round"],
        )
        return {"result": result}
