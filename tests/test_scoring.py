from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agents.logic_graph import (
    build_fallback_logic_graph,
    evaluate_evidence_graph,
    evaluate_logic_graph,
    normalize_logic_graph,
    required_assumption_node_ids,
)
from agents.models import (
    AssumptionAssessment,
    AssumptionFinding,
    AssumptionScoreState,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceSourceType,
    LogicOperator,
    NodeEvidenceVerdict,
    StructuredThesis,
    ThesisLogicGraph,
    ThesisLogicNode,
    ThesisStatus,
)
from agents.scoring import (
    calculate_score_breakdown,
    prepare_structured_thesis,
    status_from_score_delta,
)

ASSUMPTIONS = ["Demand keeps growing", "Share remains stable", "Margins remain healthy"]


def _graph(operator: LogicOperator = LogicOperator.CONTRIBUTING) -> ThesisLogicGraph:
    return ThesisLogicGraph(
        root_id="root_claim",
        nodes=[
            ThesisLogicNode(
                node_id="root_claim",
                kind="CLAIM",
                label="The business compounds intrinsic value",
                operator=operator,
                child_ids=["demand", "share", "margin"],
            ),
            ThesisLogicNode(
                node_id="demand",
                kind="ASSUMPTION",
                label=ASSUMPTIONS[0],
                assumption=ASSUMPTIONS[0],
            ),
            ThesisLogicNode(
                node_id="share",
                kind="ASSUMPTION",
                label=ASSUMPTIONS[1],
                assumption=ASSUMPTIONS[1],
            ),
            ThesisLogicNode(
                node_id="margin",
                kind="ASSUMPTION",
                label=ASSUMPTIONS[2],
                assumption=ASSUMPTIONS[2],
            ),
        ],
    )


def _thesis(operator: LogicOperator = LogicOperator.CONTRIBUTING) -> StructuredThesis:
    return prepare_structured_thesis(
        StructuredThesis(
            raw_input="Demand, share, and margins will support long-term compounding.",
            main_thesis="The business compounds intrinsic value",
            key_assumptions=ASSUMPTIONS,
            logic_graph=_graph(operator),
        )
    )


def _evidence(
    document_id: str,
    assumption: str,
    classification: EvidenceClassification,
    impact: EvidenceImpact,
) -> EvidenceItem:
    return EvidenceItem(
        document_id=document_id,
        source_type=EvidenceSourceType.NEWS,
        source_url=f"https://example.com/{document_id}",
        content_snippet="A sourced fact affects the assumption.",
        classification=classification,
        impact=impact,
        reason="Directly addresses the exact assumption.",
        related_assumptions=[assumption],
    )


def _persist(thesis: StructuredThesis, breakdown) -> StructuredThesis:
    return thesis.model_copy(
        update={
            "confidence_score": breakdown.health_score,
            "score_breakdown": breakdown,
            "status": ThesisStatus.BROKEN if breakdown.is_broken else ThesisStatus.UNCHANGED,
        }
    )


def test_graph_operators_propagate_leaf_states_deterministically() -> None:
    states = {"demand": 1.0, "share": -0.5, "margin": 0.5}
    observed = set(states)

    and_states, _ = evaluate_logic_graph(_graph(LogicOperator.AND), states, observed)
    or_states, _ = evaluate_logic_graph(_graph(LogicOperator.OR), states, observed)
    contributing_states, coverage = evaluate_logic_graph(
        _graph(LogicOperator.CONTRIBUTING), states, observed
    )

    assert and_states["root_claim"] == -0.5
    assert or_states["root_claim"] == 1.0
    assert contributing_states["root_claim"] == 1 / 3
    assert coverage["root_claim"] == 100


def test_four_value_graph_propagates_support_and_contradiction_independently() -> None:
    graph = _graph(LogicOperator.AND)
    support, contradict, _ = evaluate_evidence_graph(
        graph,
        {"demand": 0.8, "share": 0.7, "margin": 0.9},
        {"demand": 0.0, "share": 0.6, "margin": 0.0},
        {"demand", "share", "margin"},
    )

    assert support["root_claim"] == 0.7
    assert contradict["root_claim"] == 0.6


def test_legacy_assumption_state_derives_four_value_verdict() -> None:
    legacy = AssumptionScoreState.model_validate(
        {
            "assumption": ASSUMPTIONS[0],
            "node_id": "demand",
            "support_strength": 0.4,
            "contradict_strength": 0.3,
            "state": 0.1,
        }
    )

    assert legacy.verdict == NodeEvidenceVerdict.CONFLICTING


def test_invalid_graph_falls_back_to_equal_contribution_graph() -> None:
    disconnected = _graph().model_copy(
        update={
            "nodes": [
                *_graph().nodes,
                ThesisLogicNode(
                    node_id="orphan",
                    kind="ASSUMPTION",
                    label="Orphan",
                    assumption="Orphan",
                ),
            ]
        }
    )

    normalized = normalize_logic_graph(
        disconnected,
        main_thesis="The business compounds intrinsic value",
        key_assumptions=ASSUMPTIONS,
    )

    assert normalized == build_fallback_logic_graph(
        "The business compounds intrinsic value", ASSUMPTIONS
    )
    assert normalized.nodes[0].operator == LogicOperator.CONTRIBUTING


def test_incomplete_model_claim_reaches_fallback_instead_of_raising() -> None:
    incomplete = ThesisLogicGraph(
        root_id="root_claim",
        nodes=[
            ThesisLogicNode(
                node_id="root_claim",
                kind="CLAIM",
                label="The business compounds intrinsic value",
                operator=LogicOperator.AND,
            ),
            *[
                ThesisLogicNode(
                    node_id=f"assumption_{index}",
                    kind="ASSUMPTION",
                    label=assumption,
                    assumption=assumption,
                )
                for index, assumption in enumerate(ASSUMPTIONS, start=1)
            ],
        ],
    )

    normalized = normalize_logic_graph(
        incomplete,
        main_thesis="The business compounds intrinsic value",
        key_assumptions=ASSUMPTIONS,
    )

    assert normalized.nodes[0].operator == LogicOperator.CONTRIBUTING
    assert normalized.nodes[0].child_ids == ["assumption_1", "assumption_2", "assumption_3"]


def test_required_assumptions_are_derived_only_through_and_paths() -> None:
    graph = ThesisLogicGraph(
        root_id="root_claim",
        nodes=[
            ThesisLogicNode(
                node_id="root_claim",
                kind="CLAIM",
                label="Root",
                operator=LogicOperator.AND,
                child_ids=["required_leaf", "alternatives"],
            ),
            ThesisLogicNode(
                node_id="required_leaf",
                kind="ASSUMPTION",
                label=ASSUMPTIONS[0],
                assumption=ASSUMPTIONS[0],
            ),
            ThesisLogicNode(
                node_id="alternatives",
                kind="CLAIM",
                label="One route can work",
                operator=LogicOperator.OR,
                child_ids=["share", "margin"],
            ),
            ThesisLogicNode(
                node_id="share",
                kind="ASSUMPTION",
                label=ASSUMPTIONS[1],
                assumption=ASSUMPTIONS[1],
            ),
            ThesisLogicNode(
                node_id="margin",
                kind="ASSUMPTION",
                label=ASSUMPTIONS[2],
                assumption=ASSUMPTIONS[2],
            ),
        ],
    )

    assert required_assumption_node_ids(graph) == {"required_leaf"}


def test_independent_evidence_accumulates_with_reduced_strength() -> None:
    thesis = _thesis()
    result = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "support-1", ASSUMPTIONS[0], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH
            ),
            _evidence(
                "support-2", ASSUMPTIONS[0], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH
            ),
        ],
    )

    demand = result.assumption_scores[0]
    assert demand.support_strength == 0.7884
    assert demand.state == 0.7884
    assert result.root_state == 0.2628
    assert result.health_score == 63


def test_repeated_reports_of_the_same_event_count_once_across_runs() -> None:
    thesis = _thesis()
    published_at = datetime(2026, 7, 15, tzinfo=UTC)
    original = _evidence(
        "original-report",
        ASSUMPTIONS[0],
        EvidenceClassification.SUPPORT,
        EvidenceImpact.HIGH,
    ).model_copy(
        update={
            "published_at": published_at,
            "content_snippet": (
                "Apple reported third-quarter revenue of $85 billion, up 5%, "
                "as iPhone demand strengthened."
            ),
        }
    )
    repeated = _evidence(
        "repeated-report",
        ASSUMPTIONS[0],
        EvidenceClassification.SUPPORT,
        EvidenceImpact.HIGH,
    ).model_copy(
        update={
            "published_at": published_at + timedelta(days=1),
            "content_snippet": (
                "Apple's Q3 sales reached $85 billion, a 5 percent increase driven by "
                "stronger iPhone demand."
            ),
        }
    )
    later_repeat = _evidence(
        "later-repeat",
        ASSUMPTIONS[0],
        EvidenceClassification.SUPPORT,
        EvidenceImpact.HIGH,
    ).model_copy(
        update={
            "published_at": published_at + timedelta(days=2),
            "content_snippet": (
                "Strong iPhone demand helped Apple post $85 billion in quarterly sales, "
                "5 percent above the prior year."
            ),
        }
    )

    same_run = calculate_score_breakdown(thesis, [original, repeated])
    next_run = calculate_score_breakdown(_persist(thesis, same_run), [later_repeat])

    assert same_run.assumption_scores[0].support_strength == 0.54
    assert len(same_run.assumption_scores[0].evidence_event_keys) == 1
    assert next_run.assumption_scores[0].support_strength == 0.54
    assert next_run.score_delta == 0


def test_every_information_item_has_one_state_per_assumption_node() -> None:
    thesis = _thesis()
    evidence = _evidence(
        "matrix-item",
        ASSUMPTIONS[0],
        EvidenceClassification.SUPPORT,
        EvidenceImpact.HIGH,
    ).model_copy(
        update={
            "related_assumptions": ASSUMPTIONS[:2],
            "assumption_findings": [
                AssumptionFinding(
                    assumption=ASSUMPTIONS[0],
                    assessment=AssumptionAssessment.SUPPORT,
                    impact=EvidenceImpact.HIGH,
                    relevance_score=0.8,
                    reasoning="Direct demand evidence.",
                    source_passage_indices=[0],
                ),
                AssumptionFinding(
                    assumption=ASSUMPTIONS[1],
                    assessment=AssumptionAssessment.CONTRADICT,
                    impact=EvidenceImpact.MEDIUM,
                    relevance_score=0.6,
                    reasoning="Moderately challenges share stability.",
                    source_passage_indices=[1],
                ),
            ],
        }
    )

    result = calculate_score_breakdown(thesis, [evidence])

    impact = result.evidence_impacts[0]
    assert len(impact.node_contributions) == len(ASSUMPTIONS)
    assert [item.signed_strength for item in impact.node_contributions] == [0.432, -0.162, 0]
    assert impact.score_delta == result.score_delta


def test_uncited_directional_finding_does_not_change_unaddressed_node() -> None:
    thesis = _thesis()
    evidence = _evidence(
        "valuation-report",
        ASSUMPTIONS[0],
        EvidenceClassification.CONTRADICT,
        EvidenceImpact.HIGH,
    ).model_copy(
        update={
            "related_assumptions": ASSUMPTIONS[:2],
            "assumption_findings": [
                AssumptionFinding(
                    assumption=ASSUMPTIONS[0],
                    assessment=AssumptionAssessment.CONTRADICT,
                    impact=EvidenceImpact.HIGH,
                    relevance_score=0.95,
                    reasoning="The cited valuation comparison directly contradicts this node.",
                    source_passage_indices=[0],
                ),
                AssumptionFinding(
                    assumption=ASSUMPTIONS[1],
                    assessment=AssumptionAssessment.CONTRADICT,
                    impact=EvidenceImpact.HIGH,
                    relevance_score=0.95,
                    reasoning="The report does not mention this node.",
                    source_passage_indices=[],
                ),
            ],
        }
    )

    result = calculate_score_breakdown(thesis, [evidence])

    states = {item.assumption: item.state for item in result.assumption_scores}
    contributions = {
        item.assumption: item for item in result.evidence_impacts[0].node_contributions
    }
    assert states[ASSUMPTIONS[0]] == -0.513
    assert states[ASSUMPTIONS[1]] == 0
    assert contributions[ASSUMPTIONS[1]].assessment == AssumptionAssessment.NOT_ADDRESSED
    assert contributions[ASSUMPTIONS[1]].signed_strength == 0


def test_not_addressed_information_preserves_previous_node_state_and_score() -> None:
    thesis = _thesis()
    first = calculate_score_breakdown(
        thesis,
        [_evidence("support", ASSUMPTIONS[0], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH)],
    )
    persisted = _persist(thesis, first)
    unrelated = _evidence(
        "unrelated",
        ASSUMPTIONS[0],
        EvidenceClassification.NEUTRAL,
        EvidenceImpact.LOW,
    ).model_copy(
        update={
            "related_assumptions": [],
            "assumption_findings": [
                AssumptionFinding(
                    assumption=assumption,
                    assessment=AssumptionAssessment.NOT_ADDRESSED,
                    impact=EvidenceImpact.LOW,
                    relevance_score=0,
                    reasoning="The information does not address this node.",
                )
                for assumption in ASSUMPTIONS
            ],
        }
    )

    second = calculate_score_breakdown(persisted, [unrelated])

    assert second.health_score == first.health_score
    assert second.score_delta == 0
    assert second.assumption_scores == first.assumption_scores
    assert second.evidence_impacts[0].score_delta == 0


def test_information_attributions_sum_to_nonlinear_final_score_change() -> None:
    thesis = _thesis(LogicOperator.AND)
    evidence = [
        _evidence("demand", ASSUMPTIONS[0], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH),
        _evidence("share", ASSUMPTIONS[1], EvidenceClassification.SUPPORT, EvidenceImpact.MEDIUM),
        _evidence("margin", ASSUMPTIONS[2], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH),
    ]

    result = calculate_score_breakdown(thesis, evidence)

    assert round(sum(item.score_delta for item in result.evidence_impacts), 2) == result.score_delta
    assert {item.document_id for item in result.evidence_impacts} == {
        "demand",
        "share",
        "margin",
    }


def test_opposing_evidence_is_conflicting_even_when_numeric_projection_cancels() -> None:
    thesis = _thesis()
    first = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "support", ASSUMPTIONS[0], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH
            ),
            _evidence(
                "contradict",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            ),
        ],
    )
    second = calculate_score_breakdown(_persist(thesis, first), [])

    assert first.assumption_scores[0].state == 0
    assert first.assumption_scores[0].verdict == NodeEvidenceVerdict.CONFLICTING
    assert first.root_verdict == NodeEvidenceVerdict.CONFLICTING
    assert first.root_support_strength > 0
    assert first.root_contradict_strength > 0
    assert second.assumption_scores[0] == first.assumption_scores[0]
    assert second.root_verdict == NodeEvidenceVerdict.CONFLICTING
    assert second.health_score == 50


def test_two_distinct_high_contradictions_break_required_assumption() -> None:
    thesis = _thesis(LogicOperator.AND)
    first = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "contradiction-1",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            )
        ],
    )
    duplicate = calculate_score_breakdown(
        _persist(thesis, first),
        [
            _evidence(
                "contradiction-1",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            )
        ],
    )
    second = calculate_score_breakdown(
        _persist(thesis, first),
        [
            _evidence(
                "contradiction-2",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            )
        ],
    )

    assert first.assumption_scores[0].invalidation_streak == 1
    assert duplicate.assumption_scores[0].invalidation_streak == 1
    assert second.assumption_scores[0].invalidation_streak == 2
    assert second.is_broken is True
    assert second.invalidated_assumptions == [ASSUMPTIONS[0]]


def test_broken_state_latches_until_thesis_is_prepared_again() -> None:
    thesis = _thesis(LogicOperator.AND)
    first = calculate_score_breakdown(
        thesis,
        [_evidence("c1", ASSUMPTIONS[0], EvidenceClassification.CONTRADICT, EvidenceImpact.HIGH)],
    )
    broken = calculate_score_breakdown(
        _persist(thesis, first),
        [_evidence("c2", ASSUMPTIONS[0], EvidenceClassification.CONTRADICT, EvidenceImpact.HIGH)],
    )
    latched = calculate_score_breakdown(
        _persist(thesis, broken),
        [_evidence("s1", ASSUMPTIONS[0], EvidenceClassification.SUPPORT, EvidenceImpact.HIGH)],
    )
    reset = prepare_structured_thesis(_persist(thesis, broken))

    assert latched.is_broken is True
    assert reset.status == ThesisStatus.UNCHANGED
    assert reset.confidence_score == 50
    assert reset.score_breakdown is not None
    assert reset.score_breakdown.is_broken is False


def test_contributing_assumptions_do_not_trigger_hard_gate() -> None:
    thesis = _thesis(LogicOperator.CONTRIBUTING)
    first = calculate_score_breakdown(
        thesis,
        [_evidence("c1", ASSUMPTIONS[0], EvidenceClassification.CONTRADICT, EvidenceImpact.HIGH)],
    )
    second = calculate_score_breakdown(
        _persist(thesis, first),
        [_evidence("c2", ASSUMPTIONS[0], EvidenceClassification.CONTRADICT, EvidenceImpact.HIGH)],
    )

    assert first.assumption_scores[0].invalidation_streak == 0
    assert second.is_broken is False


def test_status_thresholds_remain_deterministic() -> None:
    assert status_from_score_delta(15) == ThesisStatus.STRONGLY_STRENGTHENED
    assert status_from_score_delta(5) == ThesisStatus.STRENGTHENED
    assert status_from_score_delta(4) == ThesisStatus.UNCHANGED
    assert status_from_score_delta(-5) == ThesisStatus.WEAKENED
    assert status_from_score_delta(-15) == ThesisStatus.STRONGLY_WEAKENED
