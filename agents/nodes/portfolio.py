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
    except Exception:
        analysis = PortfolioAnalysis(summary="집중도 분석 모델 응답을 확인할 수 없습니다.")
    return {"portfolio_analysis": analysis}
