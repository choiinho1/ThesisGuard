"""SEC/IR/Earnings research node."""

from langgraph.runtime import Runtime

from agents.nodes.common import run_research_tool
from agents.runtime import AgentDependencies
from agents.state import AnalysisState


async def filing_agent(state: AnalysisState, runtime: Runtime[AgentDependencies]) -> dict:
    return await run_research_tool(
        state, runtime, "filings", runtime.context.research_tools.get_filings
    )
