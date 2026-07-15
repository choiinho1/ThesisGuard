"""Validation and deterministic evaluation for thesis-specific causal graphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agents.models import (
    LogicOperator,
    NodeEvidenceVerdict,
    ThesisLogicGraph,
    ThesisLogicNode,
)

LOGIC_GRAPH_VERSION = "1.0.0"


def build_fallback_logic_graph(
    main_thesis: str,
    key_assumptions: Sequence[str],
) -> ThesisLogicGraph:
    """Create an equal-contribution graph when model output is absent or invalid."""

    leaf_nodes = [
        ThesisLogicNode(
            node_id=f"assumption_{index}",
            kind="ASSUMPTION",
            label=assumption,
            assumption=assumption,
        )
        for index, assumption in enumerate(dict.fromkeys(key_assumptions), start=1)
    ]
    return ThesisLogicGraph(
        graph_version=LOGIC_GRAPH_VERSION,
        root_id="root_claim",
        nodes=[
            ThesisLogicNode(
                node_id="root_claim",
                kind="CLAIM",
                label=main_thesis,
                operator=LogicOperator.CONTRIBUTING,
                child_ids=[node.node_id for node in leaf_nodes],
            ),
            *leaf_nodes,
        ],
    )


def normalize_logic_graph(
    graph: ThesisLogicGraph | None,
    *,
    main_thesis: str,
    key_assumptions: Sequence[str],
) -> ThesisLogicGraph:
    """Accept a complete connected DAG or replace it with a safe fallback graph."""

    assumptions = list(dict.fromkeys(key_assumptions))
    if graph is None:
        return build_fallback_logic_graph(main_thesis, assumptions)

    nodes_by_id = {node.node_id: node for node in graph.nodes}
    if len(nodes_by_id) != len(graph.nodes) or graph.root_id not in nodes_by_id:
        return build_fallback_logic_graph(main_thesis, assumptions)
    if nodes_by_id[graph.root_id].kind != "CLAIM":
        return build_fallback_logic_graph(main_thesis, assumptions)
    for node in graph.nodes:
        if node.kind == "ASSUMPTION":
            if not node.assumption or node.operator is not None or node.child_ids:
                return build_fallback_logic_graph(main_thesis, assumptions)
        elif node.assumption is not None or node.operator is None or not node.child_ids:
            return build_fallback_logic_graph(main_thesis, assumptions)

    graph_assumptions = [node.assumption for node in graph.nodes if node.kind == "ASSUMPTION"]
    if graph_assumptions != assumptions and (
        len(graph_assumptions) != len(assumptions) or set(graph_assumptions) != set(assumptions)
    ):
        return build_fallback_logic_graph(main_thesis, assumptions)

    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return False
        if node_id in visited:
            return True
        node = nodes_by_id.get(node_id)
        if node is None or len(node.child_ids) != len(set(node.child_ids)):
            return False
        visiting.add(node_id)
        if any(not visit(child_id) for child_id in node.child_ids):
            return False
        visiting.remove(node_id)
        visited.add(node_id)
        return True

    if not visit(graph.root_id) or visited != set(nodes_by_id):
        return build_fallback_logic_graph(main_thesis, assumptions)
    return graph.model_copy(update={"graph_version": LOGIC_GRAPH_VERSION})


def required_assumption_node_ids(graph: ThesisLogicGraph) -> set[str]:
    """Derive logical necessity from topology instead of model-assigned weights."""

    nodes = {node.node_id: node for node in graph.nodes}
    required: set[str] = set()

    def walk(node_id: str, path_is_required: bool) -> None:
        node = nodes[node_id]
        if node.kind == "ASSUMPTION":
            if path_is_required:
                required.add(node_id)
            return
        children_required = path_is_required and node.operator == LogicOperator.AND
        for child_id in node.child_ids:
            walk(child_id, children_required)

    walk(graph.root_id, True)
    return required


def research_target_assumption_node_ids(graph: ThesisLogicGraph) -> set[str]:
    """Return strict AND requirements, or all leaves when the graph has no strict requirement."""

    required = required_assumption_node_ids(graph)
    if required:
        return required
    return {node.node_id for node in graph.nodes if node.kind == "ASSUMPTION"}


def evaluate_logic_graph(
    graph: ThesisLogicGraph,
    assumption_states: Mapping[str, float],
    observed_assumption_ids: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Propagate leaf states and evidence coverage through fixed logical operators."""

    nodes = {node.node_id: node for node in graph.nodes}
    states: dict[str, float] = {}
    coverage: dict[str, float] = {}
    descendant_leaves: dict[str, set[str]] = {}

    def evaluate(node_id: str) -> tuple[float, set[str]]:
        node = nodes[node_id]
        if node.kind == "ASSUMPTION":
            state = float(assumption_states.get(node_id, 0.0))
            leaves = {node_id}
        else:
            child_results = [evaluate(child_id) for child_id in node.child_ids]
            child_states = [result[0] for result in child_results]
            leaves = set().union(*(result[1] for result in child_results))
            if node.operator == LogicOperator.AND:
                state = min(child_states)
            elif node.operator == LogicOperator.OR:
                state = max(child_states)
            else:
                state = sum(child_states) / len(child_states)
        states[node_id] = state
        descendant_leaves[node_id] = leaves
        coverage[node_id] = (
            len(leaves & observed_assumption_ids) / len(leaves) * 100 if leaves else 0.0
        )
        return state, leaves

    evaluate(graph.root_id)
    return states, coverage


def evidence_verdict(
    support_strength: float,
    contradict_strength: float,
) -> NodeEvidenceVerdict:
    """Classify independent support/refutation axes without cancelling conflict."""

    has_support = support_strength > 0
    has_contradiction = contradict_strength > 0
    if has_support and has_contradiction:
        return NodeEvidenceVerdict.CONFLICTING
    if has_support:
        return NodeEvidenceVerdict.SUPPORTED
    if has_contradiction:
        return NodeEvidenceVerdict.REFUTED
    return NodeEvidenceVerdict.INSUFFICIENT


def evaluate_evidence_graph(
    graph: ThesisLogicGraph,
    assumption_support: Mapping[str, float],
    assumption_contradict: Mapping[str, float],
    observed_assumption_ids: set[str],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Propagate support and contradiction separately through the causal graph."""

    nodes = {node.node_id: node for node in graph.nodes}
    support: dict[str, float] = {}
    contradict: dict[str, float] = {}
    coverage: dict[str, float] = {}

    def evaluate(node_id: str) -> tuple[float, float, set[str]]:
        node = nodes[node_id]
        if node.kind == "ASSUMPTION":
            node_support = float(assumption_support.get(node_id, 0.0))
            node_contradict = float(assumption_contradict.get(node_id, 0.0))
            leaves = {node_id}
        else:
            child_results = [evaluate(child_id) for child_id in node.child_ids]
            child_support = [result[0] for result in child_results]
            child_contradict = [result[1] for result in child_results]
            leaves = set().union(*(result[2] for result in child_results))
            if node.operator == LogicOperator.AND:
                node_support = min(child_support)
                node_contradict = max(child_contradict)
            elif node.operator == LogicOperator.OR:
                node_support = max(child_support)
                node_contradict = min(child_contradict)
            else:
                node_support = sum(child_support) / len(child_support)
                node_contradict = sum(child_contradict) / len(child_contradict)
        support[node_id] = node_support
        contradict[node_id] = node_contradict
        coverage[node_id] = (
            len(leaves & observed_assumption_ids) / len(leaves) * 100 if leaves else 0.0
        )
        return node_support, node_contradict, leaves

    evaluate(graph.root_id)
    return support, contradict, coverage
