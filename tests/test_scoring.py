from __future__ import annotations

from agents.models import (
    AssumptionBinding,
    EvidenceClassification,
    EvidenceImpact,
    EvidenceItem,
    StructuredThesis,
    ThesisStatus,
)
from agents.scoring import (
    calculate_score_breakdown,
    normalize_assumption_bindings,
    prepare_structured_thesis,
    score_thesis,
    status_from_score_delta,
)
from agents.thesis_templates import ThesisTemplateId, get_thesis_template

ASSUMPTIONS = [
    "시장 수요가 계속 성장한다",
    "회사가 점유율을 확대한다",
    "단위경제성이 개선된다",
]


def _thesis() -> StructuredThesis:
    return prepare_structured_thesis(
        StructuredThesis(
            raw_input="시장 성장과 점유율 확대가 규모의 경제를 만들 것이라는 투자 논리입니다.",
            main_thesis="시장 성장과 점유율 확대로 규모의 경제를 달성한다",
            key_assumptions=ASSUMPTIONS,
            template_id=ThesisTemplateId.SCALABLE_GROWTH,
            assumption_bindings=[
                AssumptionBinding(slot_id="market_demand", assumptions=[ASSUMPTIONS[0]]),
                AssumptionBinding(slot_id="adoption_share", assumptions=[ASSUMPTIONS[1]]),
                AssumptionBinding(slot_id="unit_economics", assumptions=[ASSUMPTIONS[2]]),
            ],
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
        source_type="EARNINGS",
        source_url=f"https://example.com/{document_id}",
        content_snippet="검증 가능한 원문",
        classification=classification,
        impact=impact,
        reason="핵심 가정을 직접 검증합니다.",
        related_assumptions=[assumption],
    )


def test_weighted_score_matches_template_formula() -> None:
    thesis = _thesis()
    breakdown = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "demand",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            ),
            _evidence(
                "share",
                ASSUMPTIONS[1],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.MEDIUM,
            ),
            _evidence(
                "economics",
                ASSUMPTIONS[2],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.MEDIUM,
            ),
        ],
    )

    assert breakdown.health_score == 66
    assert breakdown.score_delta == 16
    assert breakdown.coverage_percent == 85.0
    assert [slot.contribution_points for slot in breakdown.slot_scores] == [
        15.0,
        7.5,
        -6.3,
        0.0,
    ]
    assert status_from_score_delta(breakdown.score_delta) == ThesisStatus.STRONGLY_STRENGTHENED


def test_no_new_evidence_retains_previous_assumption_states_and_score() -> None:
    thesis = _thesis()
    first = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "demand",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            )
        ],
    )
    persisted = thesis.model_copy(
        update={"confidence_score": first.health_score, "score_breakdown": first}
    )

    second = calculate_score_breakdown(persisted, [])

    assert second.health_score == first.health_score == 65
    assert second.score_delta == 0
    assert second.assumption_scores[0].evidence_document_ids == ["demand"]


def test_new_evidence_replaces_only_the_affected_assumption_state() -> None:
    thesis = _thesis()
    first = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "demand-up",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            ),
            _evidence(
                "share-up",
                ASSUMPTIONS[1],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.MEDIUM,
            ),
        ],
    )
    persisted = thesis.model_copy(
        update={"confidence_score": first.health_score, "score_breakdown": first}
    )

    second = calculate_score_breakdown(
        persisted,
        [
            _evidence(
                "demand-down",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            )
        ],
    )

    assert second.health_score == 43
    assert second.score_delta == -30
    assert second.assumption_scores[0].state == -1.0
    assert second.assumption_scores[1].state == 0.5
    assert second.assumption_scores[1].evidence_document_ids == ["share-up"]


def test_document_count_does_not_multiply_evidence_strength() -> None:
    thesis = _thesis()
    one = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "article-1",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.MEDIUM,
            )
        ],
    )
    many = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "article-1",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.MEDIUM,
            ),
            _evidence(
                "article-2",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.MEDIUM,
            ),
        ],
    )

    assert one.health_score == many.health_score == 58


def test_equal_support_and_contradiction_cancel_with_coverage_retained() -> None:
    breakdown = calculate_score_breakdown(
        _thesis(),
        [
            _evidence(
                "support",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            ),
            _evidence(
                "contradict",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            ),
        ],
    )

    assert breakdown.health_score == 50
    assert breakdown.coverage_percent == 30.0
    assert breakdown.assumption_scores[0].state == 0.0
    assert breakdown.assumption_scores[0].has_evidence is True


def test_existing_thesis_keeps_persisted_weights_and_catalog_version() -> None:
    existing = _thesis()
    assert existing.score_breakdown is not None
    persisted_weights = {
        "market_demand": 7000,
        "adoption_share": 1000,
        "unit_economics": 1000,
        "funding_execution": 1000,
    }
    persisted_slots = [
        slot.model_copy(update={"weight_bps": persisted_weights[slot.slot_id]})
        for slot in existing.score_breakdown.slot_scores
    ]
    existing = existing.model_copy(
        update={
            "score_breakdown": existing.score_breakdown.model_copy(
                update={
                    "template_catalog_version": "0.9.0",
                    "slot_scores": persisted_slots,
                }
            )
        }
    )

    result = calculate_score_breakdown(
        existing,
        [
            _evidence(
                "support",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            )
        ],
    )

    assert result.health_score == 85
    assert result.template_catalog_version == "0.9.0"
    assert {slot.slot_id: slot.weight_bps for slot in result.slot_scores} == persisted_weights


def test_binding_normalization_rejects_unknown_paraphrased_and_duplicate_values() -> None:
    template = get_thesis_template(ThesisTemplateId.SCALABLE_GROWTH)
    normalized = normalize_assumption_bindings(
        template.template_id,
        ASSUMPTIONS,
        [
            AssumptionBinding(
                slot_id="market_demand",
                assumptions=[ASSUMPTIONS[0], "AI가 바꾼 문장"],
            ),
            AssumptionBinding(
                slot_id="adoption_share",
                assumptions=[ASSUMPTIONS[0], ASSUMPTIONS[1]],
            ),
            AssumptionBinding(slot_id="invalid_slot", assumptions=[ASSUMPTIONS[2]]),
        ],
    )

    assert [binding.slot_id for binding in normalized] == [
        slot.slot_id for slot in template.assumption_slots
    ]
    assert normalized[0].assumptions == [ASSUMPTIONS[0]]
    assert normalized[1].assumptions == [ASSUMPTIONS[1]]
    assert ASSUMPTIONS[2] not in [
        assumption for binding in normalized for assumption in binding.assumptions
    ]


def test_two_consecutive_high_contradictions_break_a_core_assumption() -> None:
    thesis = _thesis()
    first = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "first-contradiction",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            )
        ],
    )
    persisted = thesis.model_copy(
        update={"confidence_score": first.health_score, "score_breakdown": first}
    )

    result = score_thesis(
        {
            "thesis_snapshot": persisted,
            "evidence_list": [
                _evidence(
                    "second-contradiction",
                    ASSUMPTIONS[0],
                    EvidenceClassification.CONTRADICT,
                    EvidenceImpact.HIGH,
                )
            ],
        }
    )

    breakdown = result["score_breakdown"]
    assert first.assumption_scores[0].invalidation_streak == 1
    assert first.is_broken is False
    assert breakdown.assumption_scores[0].invalidation_streak == 2
    assert breakdown.invalidated_assumptions == [ASSUMPTIONS[0]]
    assert breakdown.is_broken is True
    assert result["updated_status"] == ThesisStatus.BROKEN
    assert "2회 연속" in result["deterministic_change_reason"]


def test_duplicate_or_missing_evidence_does_not_advance_invalidation_streak() -> None:
    thesis = _thesis()
    document = _evidence(
        "same-document",
        ASSUMPTIONS[0],
        EvidenceClassification.CONTRADICT,
        EvidenceImpact.HIGH,
    )
    first = calculate_score_breakdown(thesis, [document])
    persisted = thesis.model_copy(
        update={"confidence_score": first.health_score, "score_breakdown": first}
    )

    duplicate = calculate_score_breakdown(persisted, [document])
    no_evidence = calculate_score_breakdown(persisted, [])

    assert duplicate.assumption_scores[0].invalidation_streak == 1
    assert no_evidence.assumption_scores[0].invalidation_streak == 1
    assert duplicate.is_broken is False
    assert no_evidence.is_broken is False


def test_support_resets_streak_but_broken_state_is_latched_until_logic_reset() -> None:
    thesis = _thesis()
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
    after_first = thesis.model_copy(
        update={"confidence_score": first.health_score, "score_breakdown": first}
    )
    supported = calculate_score_breakdown(
        after_first,
        [
            _evidence(
                "support-before-break",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            )
        ],
    )
    assert supported.assumption_scores[0].invalidation_streak == 0
    assert supported.is_broken is False

    second = calculate_score_breakdown(
        after_first,
        [
            _evidence(
                "contradiction-2",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            )
        ],
    )
    broken = after_first.model_copy(
        update={
            "confidence_score": second.health_score,
            "score_breakdown": second,
            "status": ThesisStatus.BROKEN,
        }
    )
    after_support = calculate_score_breakdown(
        broken,
        [
            _evidence(
                "support-after-break",
                ASSUMPTIONS[0],
                EvidenceClassification.SUPPORT,
                EvidenceImpact.HIGH,
            )
        ],
    )

    assert after_support.is_broken is True
    assert after_support.invalidated_assumptions == [ASSUMPTIONS[0]]
    reset = prepare_structured_thesis(broken)
    assert reset.status == ThesisStatus.UNCHANGED
    assert reset.score_breakdown is not None
    assert reset.score_breakdown.is_broken is False
    assert reset.score_breakdown.invalidated_assumptions == []


def test_non_core_or_medium_contradiction_never_triggers_hard_gate() -> None:
    thesis = _thesis()
    first = calculate_score_breakdown(
        thesis,
        [
            _evidence(
                "non-core-1",
                ASSUMPTIONS[2],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            ),
            _evidence(
                "core-medium-1",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.MEDIUM,
            ),
        ],
    )
    persisted = thesis.model_copy(
        update={"confidence_score": first.health_score, "score_breakdown": first}
    )
    second = calculate_score_breakdown(
        persisted,
        [
            _evidence(
                "non-core-2",
                ASSUMPTIONS[2],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.HIGH,
            ),
            _evidence(
                "core-medium-2",
                ASSUMPTIONS[0],
                EvidenceClassification.CONTRADICT,
                EvidenceImpact.MEDIUM,
            ),
        ],
    )

    states = {item.assumption: item for item in second.assumption_scores}
    assert states[ASSUMPTIONS[0]].invalidation_streak == 0
    assert states[ASSUMPTIONS[2]].invalidation_streak == 0
    assert second.is_broken is False
