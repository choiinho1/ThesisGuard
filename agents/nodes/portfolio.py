"""Portfolio Thesis Concentration and Common Risk node."""

from langgraph.runtime import Runtime

from agents.models import PortfolioAnalysis, PortfolioThesis
from agents.runtime import AgentDependencies, call_model
from agents.state import AnalysisState


async def portfolio_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    updated_thesis = state["thesis_snapshot"].model_copy(
        update={
            "confidence_score": state["updated_confidence"],
            "status": state["updated_status"],
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
        analysis = await call_model(
            runtime.context, runtime.context.model.analyze_portfolio, portfolio
        )
        return {"portfolio_analysis": analysis}
    except Exception as exc:
        # Portfolio concentration is an auxiliary explanation. A provider rate limit or
        # temporary model failure must not discard the already computed holding score.
        return {
            "portfolio_analysis": PortfolioAnalysis(
                summary=(
                    "포트폴리오 공통 위험 분석을 일시적으로 완료하지 못했습니다. "
                    "개별 종목의 근거·점수·상태 계산 결과는 정상적으로 유지됩니다."
                )
            ),
            "source_errors": [f"portfolio: {type(exc).__name__}: {exc}"],
        }
