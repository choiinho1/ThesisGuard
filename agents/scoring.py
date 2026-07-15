"""Deterministic assumption-slot scoring for investment theses."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from agents.evidence_policy import is_meaningful_directional_evidence
from agents.models import (
    AssumptionBinding,
    AssumptionScoreState,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    SlotScore,
    StructuredThesis,
    ThesisScoreBreakdown,
    ThesisStatus,
)
from agents.state import AnalysisState
from agents.thesis_templates import (
    THESIS_TEMPLATE_CATALOG_VERSION,
    ThesisTemplateId,
    get_thesis_template,
)

_IMPACT_STRENGTH = {
    EvidenceImpact.MEDIUM: Decimal("0.5"),
    EvidenceImpact.HIGH: Decimal("1.0"),
}
INVALIDATION_POLICY_VERSION = "1.0.0"
INVALIDATION_STREAK_REQUIRED = 2


def normalize_assumption_bindings(
    template_id: ThesisTemplateId | str,
    key_assumptions: Iterable[str],
    proposed_bindings: Iterable[AssumptionBinding],
    *,
    slot_ids: Iterable[str] | None = None,
) -> list[AssumptionBinding]:
    """Keep only exact, unique model mappings and materialize every template slot."""

    template = get_thesis_template(template_id)
    assumptions = list(dict.fromkeys(key_assumptions))
    allowed_assumptions = set(assumptions)
    slot_order = list(slot_ids or (slot.slot_id for slot in template.assumption_slots))
    allowed_slots = set(slot_order)
    mapped: dict[str, list[str]] = {slot_id: [] for slot_id in slot_order}
    reasons: dict[str, str] = {slot_id: "" for slot_id in slot_order}
    assigned: set[str] = set()

    for binding in proposed_bindings:
        if binding.slot_id not in allowed_slots:
            continue
        if not reasons[binding.slot_id] and binding.mapping_reason.strip():
            reasons[binding.slot_id] = binding.mapping_reason.strip()
        for assumption in binding.assumptions:
            if assumption not in allowed_assumptions or assumption in assigned:
                continue
            mapped[binding.slot_id].append(assumption)
            assigned.add(assumption)

    return [
        AssumptionBinding(
            slot_id=slot_id,
            assumptions=mapped[slot_id],
            mapping_reason=reasons[slot_id],
        )
        for slot_id in slot_order
    ]


def initialize_score_breakdown(thesis: StructuredThesis) -> ThesisScoreBreakdown:
    """Build a neutral score state for a newly created or reset thesis."""

    return calculate_score_breakdown(thesis, [])


def prepare_structured_thesis(thesis: StructuredThesis) -> StructuredThesis:
    """Normalize a newly created/reset thesis and initialize its score state."""

    normalized = thesis.model_copy(
        update={
            "assumption_bindings": normalize_assumption_bindings(
                thesis.template_id,
                thesis.key_assumptions,
                thesis.assumption_bindings,
            ),
            "score_breakdown": None,
            "confidence_score": 50,
            "status": ThesisStatus.UNCHANGED,
        }
    )
    return normalized.model_copy(update={"score_breakdown": initialize_score_breakdown(normalized)})


def calculate_score_breakdown(
    thesis: StructuredThesis,
    evidence: Iterable[EvidenceItem],
) -> ThesisScoreBreakdown:
    """Update affected assumptions and aggregate them with immutable template weights.

    A newly observed assumption replaces its previous assumption state. Assumptions
    without new directional evidence retain their prior state, so a scheduled run with
    no meaningful evidence cannot reset the thesis to 50.
    """

    template = get_thesis_template(thesis.template_id)
    previous_breakdown = thesis.score_breakdown
    persisted_slots = (
        previous_breakdown.slot_scores
        if previous_breakdown
        and previous_breakdown.template_id == thesis.template_id
        and previous_breakdown.slot_scores
        else None
    )
    scoring_slots = persisted_slots or template.assumption_slots
    persisted_core_available = bool(persisted_slots and any(slot.core for slot in persisted_slots))
    template_core = {slot.slot_id: slot.core for slot in template.assumption_slots}
    core_by_slot = {
        slot.slot_id: (
            slot.core
            if not persisted_slots or persisted_core_available
            else template_core.get(slot.slot_id, False)
        )
        for slot in scoring_slots
    }
    catalog_version = (
        previous_breakdown.template_catalog_version
        if persisted_slots and previous_breakdown
        else THESIS_TEMPLATE_CATALOG_VERSION
    )
    bindings = normalize_assumption_bindings(
        thesis.template_id,
        thesis.key_assumptions,
        thesis.assumption_bindings,
        slot_ids=(slot.slot_id for slot in scoring_slots),
    )
    evidence_items = list(evidence)
    previous_by_assumption = {
        (item.slot_id, item.assumption): item
        for item in (thesis.score_breakdown.assumption_scores if thesis.score_breakdown else [])
    }

    assumption_scores: list[AssumptionScoreState] = []
    scores_by_slot: dict[str, list[AssumptionScoreState]] = {
        slot.slot_id: [] for slot in scoring_slots
    }
    for binding in bindings:
        for assumption in binding.assumptions:
            previous = previous_by_assumption.get((binding.slot_id, assumption))
            current_evidence = [
                item
                for item in evidence_items
                if assumption in item.related_assumptions
                and is_meaningful_directional_evidence(item)
            ]
            current_document_ids = list(
                dict.fromkeys(item.document_id for item in current_evidence)
            )
            has_new_document = bool(
                current_evidence
                and (
                    previous is None
                    or set(current_document_ids) - set(previous.evidence_document_ids)
                )
            )
            if current_evidence and has_new_document:
                support = max(
                    (
                        _IMPACT_STRENGTH[item.impact]
                        for item in current_evidence
                        if item.classification == EvidenceClassification.SUPPORT
                    ),
                    default=Decimal("0"),
                )
                contradict = max(
                    (
                        _IMPACT_STRENGTH[item.impact]
                        for item in current_evidence
                        if item.classification == EvidenceClassification.CONTRADICT
                    ),
                    default=Decimal("0"),
                )
                state = support - contradict
                if previous and previous.invalidation_triggered:
                    invalidation_streak = previous.invalidation_streak
                    invalidation_triggered = True
                else:
                    severe_core_contradiction = (
                        core_by_slot.get(binding.slot_id, False)
                        and contradict == Decimal("1.0")
                        and contradict > support
                    )
                    invalidation_streak = (
                        (previous.invalidation_streak if previous else 0) + 1
                        if severe_core_contradiction
                        else 0
                    )
                    invalidation_triggered = invalidation_streak >= INVALIDATION_STREAK_REQUIRED
                score = AssumptionScoreState(
                    assumption=assumption,
                    slot_id=binding.slot_id,
                    support_strength=float(support),
                    contradict_strength=float(contradict),
                    state=float(state),
                    has_evidence=True,
                    evidence_document_ids=current_document_ids,
                    invalidation_streak=invalidation_streak,
                    invalidation_triggered=invalidation_triggered,
                )
            else:
                score = previous or AssumptionScoreState(
                    assumption=assumption,
                    slot_id=binding.slot_id,
                )
            assumption_scores.append(score)
            scores_by_slot[binding.slot_id].append(score)

    slot_scores: list[SlotScore] = []
    total_contribution = Decimal("0")
    total_coverage = Decimal("0")
    for slot in scoring_slots:
        scores = scores_by_slot[slot.slot_id]
        if scores:
            state = sum(Decimal(str(item.state)) for item in scores) / Decimal(len(scores))
            observed = sum(item.has_evidence for item in scores)
            coverage = Decimal(observed) / Decimal(len(scores)) * Decimal("100")
        else:
            state = Decimal("0")
            coverage = Decimal("0")
        weight = Decimal(slot.weight_bps) / Decimal("10000")
        contribution = Decimal("50") * weight * state
        total_contribution += contribution
        total_coverage += weight * coverage
        slot_scores.append(
            SlotScore(
                slot_id=slot.slot_id,
                label_ko=slot.label_ko,
                weight_bps=slot.weight_bps,
                core=core_by_slot.get(slot.slot_id, False),
                state=float(state),
                contribution_points=float(
                    contribution.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                ),
                coverage_percent=float(coverage.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
            )
        )

    has_bound_assumption = any(binding.assumptions for binding in bindings)
    if not has_bound_assumption and thesis.score_breakdown is None:
        health_score = thesis.confidence_score
    else:
        health_score = int(
            (Decimal("50") + total_contribution).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    health_score = min(100, max(0, health_score))
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
    return ThesisScoreBreakdown(
        template_id=thesis.template_id,
        template_catalog_version=catalog_version,
        previous_score=previous_score,
        health_score=health_score,
        score_delta=health_score - previous_score,
        coverage_percent=float(total_coverage.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
        invalidation_policy_version=INVALIDATION_POLICY_VERSION,
        is_broken=is_broken,
        invalidated_assumptions=invalidated_assumptions,
        assumption_scores=assumption_scores,
        slot_scores=slot_scores,
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
        assumptions = ", ".join(breakdown.invalidated_assumptions) or "기존 무효화 가정"
        return (
            f"Core 가정 '{assumptions}'이 HIGH 반박 근거로 "
            f"{INVALIDATION_STREAK_REQUIRED}회 연속 확인되어 투자 논리를 BROKEN으로 판정했습니다. "
            "논리를 재설정하기 전까지 이 상태를 유지합니다."
        )
    sign = "+" if breakdown.score_delta > 0 else ""
    return (
        f"템플릿 가중 점수가 {breakdown.previous_score}점에서 "
        f"{breakdown.health_score}점으로 {sign}{breakdown.score_delta}점 변했습니다. "
        f"근거 충족도는 {breakdown.coverage_percent:.1f}%입니다."
    )


def score_thesis(state: AnalysisState) -> dict:
    breakdown = calculate_score_breakdown(
        state["thesis_snapshot"],
        state.get("evidence_list", []),
    )
    conflicting = [
        item.assumption
        for item in breakdown.assumption_scores
        if item.contradict_strength > item.support_strength
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
