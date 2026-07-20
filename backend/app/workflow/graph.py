"""
Wires the six nodes into the LangGraph pipeline:

    Research --> Evidence Extraction --> Evidence Classification
             --> Bull Analysis --> Bear Analysis --> Judge --> END

Research is mock; every other node makes a real OpenAI API call (see the
docstring at the top of each node_*.py file). Thesis persistence (writing the
Judge's verdict as a new ThesisVersion + Evidence rows) happens in main.py
after `analysis_graph.invoke(...)` returns, keeping this module a pure
graph definition.
"""
from langgraph.graph import StateGraph, END

from .state import ThesisWorkflowState
from .node_research import run_research
from .node_evidence_extraction import run_evidence_extraction
from .node_evidence_classification import run_evidence_classification
from .node_bull_analysis import run_bull_analysis
from .node_bear_analysis import run_bear_analysis
from .node_judge import run_judge


def build_analysis_graph():
    graph = StateGraph(ThesisWorkflowState)

    graph.add_node("research", run_research)
    graph.add_node("evidence_extraction", run_evidence_extraction)
    graph.add_node("evidence_classification", run_evidence_classification)
    graph.add_node("bull_analysis", run_bull_analysis)
    graph.add_node("bear_analysis", run_bear_analysis)
    graph.add_node("judge", run_judge)

    graph.set_entry_point("research")
    graph.add_edge("research", "evidence_extraction")
    graph.add_edge("evidence_extraction", "evidence_classification")
    graph.add_edge("evidence_classification", "bull_analysis")
    graph.add_edge("bull_analysis", "bear_analysis")
    graph.add_edge("bear_analysis", "judge")
    graph.add_edge("judge", END)

    return graph.compile()


analysis_graph = build_analysis_graph()
