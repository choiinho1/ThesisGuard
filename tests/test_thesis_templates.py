from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.thesis_templates import (
    THESIS_TEMPLATE_CATALOG,
    THESIS_TEMPLATE_CATALOG_VERSION,
    WEIGHT_BASIS_POINTS,
    ThesisTemplateId,
    ThesisTypeTemplate,
    build_thesis_template_snapshot,
    get_thesis_template,
    list_thesis_templates,
    thesis_template_selection_guide,
)


def test_catalog_contains_every_template_id_once() -> None:
    templates = list_thesis_templates()

    assert len(templates) == len(ThesisTemplateId)
    assert set(THESIS_TEMPLATE_CATALOG) == set(ThesisTemplateId)
    assert len({template.template_id for template in templates}) == len(templates)


@pytest.mark.parametrize("template", list_thesis_templates())
def test_template_weights_and_core_slots_are_valid(template: ThesisTypeTemplate) -> None:
    assert sum(slot.weight_bps for slot in template.assumption_slots) == WEIGHT_BASIS_POINTS
    assert 1 <= sum(slot.core for slot in template.assumption_slots) <= 2
    assert len({slot.slot_id for slot in template.assumption_slots}) == len(
        template.assumption_slots
    )
    assert all(slot.suggested_metrics for slot in template.assumption_slots)
    assert all(slot.invalidation_rule_hint for slot in template.assumption_slots)


def test_template_can_be_resolved_from_serialized_string_id() -> None:
    template = get_thesis_template("TURNAROUND")

    assert template.template_id == ThesisTemplateId.TURNAROUND
    assert template.name_ko == "턴어라운드"


def test_unknown_template_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        get_thesis_template("AI_GUESSED_TEMPLATE")


def test_catalog_models_are_immutable() -> None:
    template = get_thesis_template(ThesisTemplateId.SCALABLE_GROWTH)

    with pytest.raises(ValidationError):
        template.name_ko = "변경된 이름"


def test_snapshot_preserves_catalog_version_and_exact_weights() -> None:
    snapshot = build_thesis_template_snapshot(ThesisTemplateId.TURNAROUND)

    assert snapshot["catalog_version"] == THESIS_TEMPLATE_CATALOG_VERSION
    assert snapshot["template_id"] == "TURNAROUND"
    assert sum(slot["weight_bps"] for slot in snapshot["assumption_slots"]) == 10_000


def test_selection_guide_mentions_every_allowed_template() -> None:
    guide = thesis_template_selection_guide()

    assert all(template_id.value in guide for template_id in ThesisTemplateId)
