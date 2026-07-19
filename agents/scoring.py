"""Deterministic scoring over an evidence-by-node matrix and causal graph."""

from __future__ import annotations

import hashlib
import itertools
import random
import re
from collections.abc import Iterable, Sequence
from datetime import UTC
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agents.logic_graph import (
    apply_logic_operator_guardrails,
    evaluate_evidence_graph,
    evidence_verdict,
    normalize_logic_graph,
    required_assumption_node_ids,
)
from agents.models import (
    AssumptionAssessment,
    AssumptionScoreState,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    EvidenceNodeContribution,
    EvidenceScoreImpact,
    LogicNodeScore,
    NodeEvidenceVerdict,
    StructuredThesis,
    ThesisLogicGraph,
    ThesisScoreBreakdown,
    ThesisStatus,
)
from agents.state import AnalysisState

_IMPACT_STRENGTH = {
    EvidenceImpact.LOW: Decimal("0.09"),
    EvidenceImpact.MEDIUM: Decimal("0.27"),
    EvidenceImpact.HIGH: Decimal("0.54"),
}
INVALIDATION_POLICY_VERSION = "2.0.0"
INVALIDATION_STREAK_REQUIRED = 2
_ATTRIBUTION_PERMUTATIONS = 128
_EVENT_KEY_VERSION = "v1"
_EVENT_MATCH_WINDOW_DAYS = 7
_EVENT_SIMHASH_DISTANCE = 12
_EVENT_TOKEN = re.compile(r"[^\W_]+(?:[.%+-][^\W_]+)*", re.UNICODE)
_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid")


def _canonical_reference(item: EvidenceItem) -> str:
    if item.vector_doc_id:
        return f"vector:{item.vector_doc_id}"
    if item.source_url:
        parts = urlsplit(str(item.source_url))
        query = urlencode(
            sorted(
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
            )
        )
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), parts.path, query, ""))
    return f"document:{item.document_id}"


def _content_simhash(text: str) -> int:
    """Return a stable near-duplicate fingerprint for one grounded evidence summary."""

    tokens = [token.casefold() for token in _EVENT_TOKEN.findall(text)]
    features = [(token, 2) for token in tokens]
    features.extend(
        (f"{left}\x1f{right}", 1) for left, right in zip(tokens, tokens[1:], strict=False)
    )
    if not features:
        features = [(text.casefold().strip() or "empty", 1)]

    vector = [0] * 64
    for feature, weight in features:
        value = int.from_bytes(
            hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big"
        )
        for bit in range(64):
            vector[bit] += weight if value & (1 << bit) else -weight

    fingerprint = 0
    for bit, value in enumerate(vector):
        if value >= 0:
            fingerprint |= 1 << bit
    return fingerprint


def _event_key(item: EvidenceItem, contribution: EvidenceNodeContribution) -> str:
    direction = "+" if contribution.signed_strength > 0 else "-"
    if item.published_at is None:
        reference_hash = hashlib.sha256(_canonical_reference(item).encode("utf-8")).hexdigest()[:16]
        return f"{direction}|source|{_EVENT_KEY_VERSION}|{reference_hash}"

    published_at = item.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    day = published_at.astimezone(UTC).date().toordinal()
    fingerprint = _content_simhash(item.content_snippet)
    numbers = sorted(
        {
            token.casefold().strip(".%+-")
            for token in _EVENT_TOKEN.findall(item.content_snippet)
            if any(character.isdigit() for character in token)
        }
    )
    return f"{direction}|event|{_EVENT_KEY_VERSION}|{day}|{fingerprint:016x}|{','.join(numbers)}"


def _same_event(left: str, right: str) -> bool:
    left_parts = left.split("|")
    right_parts = right.split("|")
    if len(left_parts) < 4 or len(right_parts) < 4:
        return left == right
    if left_parts[:3] != right_parts[:3]:
        return False
    if left_parts[1] == "source":
        return left == right
    if len(left_parts) not in {5, 6} or len(right_parts) not in {5, 6}:
        return left == right
    try:
        day_distance = abs(int(left_parts[3]) - int(right_parts[3]))
        hash_distance = (int(left_parts[4], 16) ^ int(right_parts[4], 16)).bit_count()
    except ValueError:
        return left == right
    if day_distance > _EVENT_MATCH_WINDOW_DAYS:
        return False
    if hash_distance <= _EVENT_SIMHASH_DISTANCE:
        return True
    left_numbers = set(left_parts[5].split(",")) - {""} if len(left_parts) == 6 else set()
    right_numbers = set(right_parts[5].split(",")) - {""} if len(right_parts) == 6 else set()
    numeric_overlap = len(left_numbers & right_numbers) / max(1, len(left_numbers | right_numbers))
    return bool(left_numbers and right_numbers and numeric_overlap >= 0.5 and hash_distance <= 32)


def _independent_edges(
    edges: Iterable[tuple[str, EvidenceNodeContribution, str]],
    prior_event_keys: Iterable[str],
) -> tuple[list[tuple[str, EvidenceNodeContribution, str]], list[str]]:
    """Keep one strongest representative for each independent event."""

    prior = list(prior_event_keys)
    representatives: list[tuple[str, EvidenceNodeContribution, str]] = []
    for edge in sorted(edges, key=lambda value: value[0]):
        document_id, contribution, event_key = edge
        if any(_same_event(event_key, previous_key) for previous_key in prior):
            continue
        matching_index = next(
            (
                index
                for index, (_, _, accepted_key) in enumerate(representatives)
                if _same_event(event_key, accepted_key)
            ),
            None,
        )
        if matching_index is None:
            representatives.append(edge)
            continue
        previous = representatives[matching_index]
        if (abs(contribution.signed_strength), document_id) > (
            abs(previous[1].signed_strength),
            previous[0],
        ):
            representatives[matching_index] = edge
    return representatives, [event_key for _, _, event_key in representatives]


def initialize_score_breakdown(thesis: StructuredThesis) -> ThesisScoreBreakdown:
    """Build a neutral graph score state for a newly created or reset thesis."""

    return calculate_score_breakdown(thesis, [])


def prepare_structured_thesis(thesis: StructuredThesis) -> StructuredThesis:
    """Validate/fallback the graph and reset scoring when thesis logic changes."""

    graph = normalize_logic_graph(
        thesis.logic_graph,
        main_thesis=thesis.main_thesis,
        key_assumptions=thesis.key_assumptions,
    )
    graph = apply_logic_operator_guardrails(graph, raw_input=thesis.raw_input)
    normalized = thesis.model_copy(
        update={
            "logic_graph": graph,
            "score_breakdown": None,
            "confidence_score": 0,
            "status": ThesisStatus.UNCHANGED,
        }
    )
    return normalized.model_copy(update={"score_breakdown": initialize_score_breakdown(normalized)})


def _signed_strength(
    assessment: AssumptionAssessment,
    impact: EvidenceImpact,
    relevance_score: float,
    impact_strength: dict[EvidenceImpact, Decimal] | None = None,
) -> float:
    direction = {
        AssumptionAssessment.SUPPORT: Decimal("1"),
        AssumptionAssessment.CONTRADICT: Decimal("-1"),
    }.get(assessment, Decimal("0"))
    weights = impact_strength or _IMPACT_STRENGTH
    strength = direction * weights[impact] * Decimal(str(relevance_score))
    return float(strength.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _node_contributions(
    graph: ThesisLogicGraph,
    item: EvidenceItem,
    impact_strength: dict[EvidenceImpact, Decimal] | None = None,
) -> list[EvidenceNodeContribution]:
    """Return one matrix cell for every assumption node, including zero cells."""

    findings = {finding.assumption: finding for finding in item.assumption_findings}
    result: list[EvidenceNodeContribution] = []
    for node in graph.nodes:
        if node.kind != "ASSUMPTION":
            continue
        assumption = node.assumption or node.label
        finding = findings.get(assumption)
        if finding is not None:
            if (
                finding.assessment
                in {AssumptionAssessment.SUPPORT, AssumptionAssessment.CONTRADICT}
                and not finding.source_passage_indices
            ):
                assessment = AssumptionAssessment.NOT_ADDRESSED
                impact = EvidenceImpact.LOW
                relevance_score = 0.0
            else:
                assessment = finding.assessment
                impact = finding.impact
                relevance_score = finding.relevance_score
        elif assumption in item.related_assumptions:
            assessment = {
                EvidenceClassification.SUPPORT: AssumptionAssessment.SUPPORT,
                EvidenceClassification.CONTRADICT: AssumptionAssessment.CONTRADICT,
            }.get(item.classification, AssumptionAssessment.NOT_ADDRESSED)
            impact = item.impact
            relevance_score = 1.0 if assessment != AssumptionAssessment.NOT_ADDRESSED else 0.0
        else:
            assessment = AssumptionAssessment.NOT_ADDRESSED
            impact = EvidenceImpact.LOW
            relevance_score = 0.0
        result.append(
            EvidenceNodeContribution(
                node_id=node.node_id,
                assumption=assumption,
                assessment=assessment,
                impact=impact,
                relevance_score=relevance_score,
                signed_strength=_signed_strength(
                    assessment, impact, relevance_score, impact_strength
                ),
            )
        )
    return result


def _combine_strength(base: float, additions: Iterable[float]) -> float:
    """Combine corroborating information with deterministic diminishing returns."""

    remaining = Decimal("1") - Decimal(str(base))
    for value in additions:
        remaining *= Decimal("1") - Decimal(str(value))
    combined = Decimal("1") - remaining
    return float(combined.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _health_score(root_state: float) -> int:
    score = (Decimal("50") * Decimal(str(root_state))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return min(50, max(-50, int(score)))


def _attribution_orders(document_ids: Sequence[str]) -> list[tuple[str, ...]]:
    """Use exact Shapley orders for small sets and stable sampling for larger sets."""

    ordered = tuple(sorted(document_ids))
    if len(ordered) <= 7:
        return list(itertools.permutations(ordered))
    seed = int.from_bytes(hashlib.sha256("\x1f".join(ordered).encode()).digest()[:8], "big")
    rng = random.Random(seed)
    orders: list[tuple[str, ...]] = [ordered, tuple(reversed(ordered))]
    while len(orders) < _ATTRIBUTION_PERMUTATIONS:
        candidate = list(ordered)
        rng.shuffle(candidate)
        order = tuple(candidate)
        if order not in orders:
            orders.append(order)
    return orders


def _attribute_score_delta(
    *,
    graph: ThesisLogicGraph,
    evidence_items: list[EvidenceItem],
    contributions_by_document: dict[str, list[EvidenceNodeContribution]],
    previous_by_node: dict[str, AssumptionScoreState],
    final_score: int,
    previous_score: int,
) -> list[EvidenceScoreImpact]:
    """Attribute the nonlinear graph movement to information using deterministic Shapley values."""

    evidence_by_document = {item.document_id: item for item in evidence_items}
    all_document_ids = list(dict.fromkeys(item.document_id for item in evidence_items))
    active_document_ids = [
        document_id
        for document_id in all_document_ids
        if any(
            contribution.signed_strength
            and document_id
            not in set(
                previous_by_node.get(
                    contribution.node_id,
                    AssumptionScoreState(
                        assumption=contribution.assumption,
                        node_id=contribution.node_id,
                    ),
                ).evidence_document_ids
            )
            for contribution in contributions_by_document[document_id]
        )
    ]
    score_cache: dict[frozenset[str], int] = {}

    def coalition_score(selected: frozenset[str]) -> int:
        if selected in score_cache:
            return score_cache[selected]
        support_by_node: dict[str, float] = {}
        contradict_by_node: dict[str, float] = {}
        for node in graph.nodes:
            if node.kind != "ASSUMPTION":
                continue
            previous = previous_by_node.get(node.node_id)
            prior_ids = set(previous.evidence_document_ids if previous else [])
            node_edges, _ = _independent_edges(
                (
                    (
                        document_id,
                        contribution,
                        _event_key(evidence_by_document[document_id], contribution),
                    )
                    for document_id in selected
                    if document_id not in prior_ids
                    for contribution in contributions_by_document[document_id]
                    if contribution.node_id == node.node_id and contribution.signed_strength
                ),
                previous.evidence_event_keys if previous else (),
            )
            contributions = [contribution for _, contribution, _ in node_edges]
            support = _combine_strength(
                previous.support_strength if previous else 0,
                (edge.signed_strength for edge in contributions if edge.signed_strength > 0),
            )
            contradict = _combine_strength(
                previous.contradict_strength if previous else 0,
                (-edge.signed_strength for edge in contributions if edge.signed_strength < 0),
            )
            support_by_node[node.node_id] = support
            contradict_by_node[node.node_id] = contradict
        graph_support, graph_contradict, _ = evaluate_evidence_graph(
            graph,
            support_by_node,
            contradict_by_node,
            set(support_by_node),
        )
        root_state = graph_support[graph.root_id] - graph_contradict[graph.root_id]
        score_cache[selected] = _health_score(root_state)
        return score_cache[selected]

    attributed = dict.fromkeys(all_document_ids, 0.0)
    if active_document_ids:
        orders = _attribution_orders(active_document_ids)
        for order in orders:
            selected: set[str] = set()
            running_score = coalition_score(frozenset())
            for document_id in order:
                selected.add(document_id)
                next_score = coalition_score(frozenset(selected))
                attributed[document_id] += next_score - running_score
                running_score = next_score
        attributed = {document_id: value / len(orders) for document_id, value in attributed.items()}

        # Legacy aggregate states can differ slightly from the stored integer score.
        # Reconcile that residual so displayed information impacts sum to the actual move.
        residual = (final_score - previous_score) - sum(attributed.values())
        anchor = max(active_document_ids, key=lambda item: abs(attributed[item]))
        attributed[anchor] += residual

    rounded = {document_id: round(value, 2) for document_id, value in attributed.items()}
    if active_document_ids:
        rounding_residual = round((final_score - previous_score) - sum(rounded.values()), 2)
        anchor = max(active_document_ids, key=lambda item: abs(rounded[item]))
        rounded[anchor] = round(rounded[anchor] + rounding_residual, 2)

    return [
        EvidenceScoreImpact(
            document_id=document_id,
            score_delta=rounded[document_id],
            node_contributions=contributions_by_document[document_id],
        )
        for document_id in all_document_ids
    ]


def calculate_score_breakdown(
    thesis: StructuredThesis,
    evidence: Iterable[EvidenceItem],
    *,
    impact_strength: dict[EvidenceImpact, Decimal] | None = None,
    invalidation_streak_required: int | None = None,
) -> ThesisScoreBreakdown:
    """Aggregate every evidence-node cell, propagate graph state, and attribute movement."""

    graph = normalize_logic_graph(
        thesis.logic_graph,
        main_thesis=thesis.main_thesis,
        key_assumptions=thesis.key_assumptions,
    )
    required_node_ids = required_assumption_node_ids(graph)
    previous_breakdown = thesis.score_breakdown
    previous_by_node = {
        item.node_id: item
        for item in (previous_breakdown.assumption_scores if previous_breakdown else [])
    }
    evidence_items = list(evidence)
    contributions_by_document = {
        item.document_id: _node_contributions(graph, item, impact_strength)
        for item in evidence_items
    }
    streak_required = invalidation_streak_required or INVALIDATION_STREAK_REQUIRED
    assumption_scores: list[AssumptionScoreState] = []

    for node in graph.nodes:
        if node.kind != "ASSUMPTION":
            continue
        assumption = node.assumption or node.label
        previous = previous_by_node.get(node.node_id)
        prior_ids = set(previous.evidence_document_ids if previous else [])
        raw_current_edges = [
            (
                item.document_id,
                contribution,
                _event_key(item, contribution),
            )
            for item in evidence_items
            if item.document_id not in prior_ids
            for contribution in contributions_by_document[item.document_id]
            if contribution.node_id == node.node_id and contribution.signed_strength
        ]
        current_edges, current_event_keys = _independent_edges(
            raw_current_edges,
            previous.evidence_event_keys if previous else (),
        )
        support = _combine_strength(
            previous.support_strength if previous else 0,
            (
                contribution.signed_strength
                for _, contribution, _ in current_edges
                if contribution.signed_strength > 0
            ),
        )
        contradict = _combine_strength(
            previous.contradict_strength if previous else 0,
            (
                -contribution.signed_strength
                for _, contribution, _ in current_edges
                if contribution.signed_strength < 0
            ),
        )
        current_document_ids = list(
            dict.fromkeys(document_id for document_id, _, _ in raw_current_edges)
        )
        severe_required_contradiction = (
            node.node_id in required_node_ids
            and any(
                contribution.assessment == AssumptionAssessment.CONTRADICT
                and contribution.impact == EvidenceImpact.HIGH
                and contribution.relevance_score >= 0.75
                for _, contribution, _ in current_edges
            )
            and contradict > support
        )
        if previous and previous.invalidation_triggered:
            invalidation_streak = previous.invalidation_streak
            invalidation_triggered = True
        elif previous and not current_edges:
            invalidation_streak = previous.invalidation_streak
            invalidation_triggered = previous.invalidation_triggered
        else:
            invalidation_streak = (
                (previous.invalidation_streak if previous else 0) + 1
                if severe_required_contradiction
                else 0
            )
            invalidation_triggered = invalidation_streak >= streak_required
        assumption_scores.append(
            AssumptionScoreState(
                assumption=assumption,
                node_id=node.node_id,
                support_strength=support,
                contradict_strength=contradict,
                state=max(-1, min(1, support - contradict)),
                verdict=evidence_verdict(support, contradict),
                has_evidence=bool((previous and previous.has_evidence) or current_edges),
                evidence_document_ids=list(
                    dict.fromkeys(
                        [
                            *(previous.evidence_document_ids if previous else []),
                            *current_document_ids,
                        ]
                    )
                ),
                evidence_event_keys=list(
                    dict.fromkeys(
                        [
                            *(previous.evidence_event_keys if previous else []),
                            *current_event_keys,
                        ]
                    )
                ),
                invalidation_streak=invalidation_streak,
                invalidation_triggered=invalidation_triggered,
            )
        )

    support_by_node, contradict_by_node, coverage_by_node = evaluate_evidence_graph(
        graph,
        {item.node_id: item.support_strength for item in assumption_scores},
        {item.node_id: item.contradict_strength for item in assumption_scores},
        {item.node_id for item in assumption_scores if item.has_evidence},
    )
    states = {
        node_id: max(-1, min(1, support_by_node[node_id] - contradict_by_node[node_id]))
        for node_id in support_by_node
    }
    root_support_strength = support_by_node[graph.root_id]
    root_contradict_strength = contradict_by_node[graph.root_id]
    root_state = states[graph.root_id]
    health_score = _health_score(root_state)
    previous_score = thesis.confidence_score
    newly_invalidated = [
        item.assumption for item in assumption_scores if item.invalidation_triggered
    ]
    prior_invalidated = previous_breakdown.invalidated_assumptions if previous_breakdown else []
    invalidated_assumptions = list(dict.fromkeys([*prior_invalidated, *newly_invalidated]))
    is_broken = bool(
        thesis.status == ThesisStatus.BROKEN
        or (previous_breakdown and previous_breakdown.is_broken)
        or invalidated_assumptions
    )
    node_scores = [
        LogicNodeScore(
            node_id=node.node_id,
            label=node.label,
            kind=node.kind,
            operator=node.operator,
            support_strength=support_by_node[node.node_id],
            contradict_strength=contradict_by_node[node.node_id],
            state=states[node.node_id],
            verdict=evidence_verdict(
                support_by_node[node.node_id],
                contradict_by_node[node.node_id],
            ),
            coverage_percent=round(coverage_by_node[node.node_id], 1),
            required=node.node_id in required_node_ids,
        )
        for node in graph.nodes
    ]
    evidence_impacts = _attribute_score_delta(
        graph=graph,
        evidence_items=evidence_items,
        contributions_by_document=contributions_by_document,
        previous_by_node=previous_by_node,
        final_score=health_score,
        previous_score=previous_score,
    )
    return ThesisScoreBreakdown(
        logic_graph_version=graph.graph_version,
        previous_score=previous_score,
        health_score=health_score,
        score_delta=health_score - previous_score,
        root_support_strength=root_support_strength,
        root_contradict_strength=root_contradict_strength,
        root_state=root_state,
        root_verdict=evidence_verdict(root_support_strength, root_contradict_strength),
        coverage_percent=round(coverage_by_node[graph.root_id], 1),
        invalidation_policy_version=INVALIDATION_POLICY_VERSION,
        is_broken=is_broken,
        invalidated_assumptions=invalidated_assumptions,
        assumption_scores=assumption_scores,
        node_scores=node_scores,
        evidence_impacts=evidence_impacts,
    )


def status_from_score_delta(delta: int) -> ThesisStatus:
    if delta >= 15:
        return ThesisStatus.STRONGLY_STRENGTHENED
    if delta >= 5:
        return ThesisStatus.STRENGTHENED
    if delta <= -15:
        return ThesisStatus.STRONGLY_WEAKENED
    if delta <= -5:
        return ThesisStatus.WEAKENED
    return ThesisStatus.UNCHANGED


def deterministic_change_reason(breakdown: ThesisScoreBreakdown) -> str:
    if breakdown.is_broken:
        assumptions = ", ".join(breakdown.invalidated_assumptions) or "중요하게 보던 기대"
        return (
            f"그동안 중요하게 보던 '{assumptions}'와 어긋나는 내용이 연이어 확인됐습니다. "
            "이전에는 이 기대를 더 지켜볼 수 있었지만, 이제는 기존 판단을 그대로 유지하기 "
            "어려운 상황입니다."
        )

    supported = [
        item.assumption
        for item in breakdown.assumption_scores
        if item.verdict == NodeEvidenceVerdict.SUPPORTED
    ]
    challenged = [
        item.assumption
        for item in breakdown.assumption_scores
        if item.verdict in {NodeEvidenceVerdict.REFUTED, NodeEvidenceVerdict.CONFLICTING}
    ]

    def expectations(items: list[str], fallback: str) -> str:
        quoted = [f"'{item}'" for item in items[:2]]
        if not quoted:
            return fallback
        if len(items) > 2:
            quoted.append("그 밖의 기대")
        return ", ".join(quoted)

    if breakdown.score_delta > 0:
        subject = expectations(supported, "기존에 기대했던 흐름")
        return (
            f"기존에는 {subject} 같은 기대가 실제로 이어질지 지켜보는 상황이었지만, 이번에는 이를 "
            f"뒷받침하는 내용이 더 확인됐습니다. 그 결과 확신도는 {breakdown.previous_score}점에서 "
            f"{breakdown.health_score}점으로 높아졌습니다."
        )
    if breakdown.score_delta < 0:
        subject = expectations(challenged, "기존에 기대했던 흐름")
        return (
            f"기존에는 {subject} 같은 흐름을 기대했지만, 이번에는 그 기대와 어긋나는 내용이 "
            f"확인됐습니다. 그 결과 확신도는 {breakdown.previous_score}점에서 "
            f"{breakdown.health_score}점으로 낮아졌습니다."
        )
    if breakdown.root_verdict == NodeEvidenceVerdict.CONFLICTING:
        subject = expectations(challenged, "기존에 기대했던 흐름")
        return (
            f"기존에는 {subject} 같은 흐름을 기대했지만, 이번에는 이에 부합하는 내용과 우려할 "
            f"내용이 함께 확인됐습니다. 어느 한쪽도 기존 판단을 바꿀 만큼 뚜렷하지 않아 "
            f"확신도는 {breakdown.health_score}점으로 유지됐습니다."
        )
    return (
        "기존에는 지금까지 확인된 내용에 따라 현재 판단을 유지하고 있었고, 이번에 확인된 "
        "자료에도 이를 바꿀 만큼 분명한 새 내용이 없었습니다. "
        f"따라서 확신도는 {breakdown.health_score}점으로 유지됐습니다."
    )


def score_thesis(
    state: AnalysisState,
    *,
    impact_strength: dict[EvidenceImpact, Decimal] | None = None,
    invalidation_streak_required: int | None = None,
) -> dict:
    breakdown = calculate_score_breakdown(
        state["thesis_snapshot"],
        state.get("evidence_list", []),
        impact_strength=impact_strength,
        invalidation_streak_required=invalidation_streak_required,
    )
    conflicting = [
        item.assumption
        for item in breakdown.assumption_scores
        if item.verdict in {NodeEvidenceVerdict.REFUTED, NodeEvidenceVerdict.CONFLICTING}
    ]
    return {
        "score_breakdown": breakdown,
        "updated_confidence": breakdown.health_score,
        "updated_status": (
            ThesisStatus.BROKEN
            if breakdown.is_broken
            else status_from_score_delta(breakdown.score_delta)
        ),
        "deterministic_change_reason": deterministic_change_reason(breakdown),
        "deterministic_conflicting_assumptions": conflicting,
    }
