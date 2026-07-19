"""Materialize DB evidence history as non-scoring narrative context files."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings
from thesisguard_backend.evidence_vector_store import delete_thesis_evidence_vectors


@dataclass(frozen=True, slots=True)
class EvidenceHistorySnapshot:
    summary: str
    document_ids: list[str]
    source_urls: list[str]
    path: Path


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _one_line(value: object, *, max_length: int = 500) -> str:
    normalized = " ".join(str(value or "").split()).replace("|", "\\|")
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1].rstrip()}…"


def _date(value: datetime | None) -> str:
    if value is None:
        return "날짜 미상"
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.isoformat(timespec="seconds")


def _sort_timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def is_duplicate_placeholder(row: orm.Evidence) -> bool:
    """Identify legacy rows that represented exclusion, not an assessment."""

    reason = str(row.reason or "")
    snippet = str(row.content_snippet or "")
    return "동일 document_id" in reason or "이번 판단에서 중복 제외" in snippet


def select_substantive_evidence(
    evidence_rows: list[orm.Evidence], *, max_items: int | None = None
) -> list[orm.Evidence]:
    """Keep the latest real assessment per document and discard legacy placeholders."""

    latest_by_document: dict[str, orm.Evidence] = {}
    for row in evidence_rows:
        if is_duplicate_placeholder(row):
            continue
        latest_by_document[row.document_id] = row
    selected = sorted(
        latest_by_document.values(),
        key=lambda row: (_sort_timestamp(row.published_at or row.created_at), row.document_id),
    )
    return selected[-max_items:] if max_items is not None else selected


def _history_path(holding_id: uuid.UUID, history_dir: Path | None = None) -> Path:
    directory = history_dir or get_settings().evidence_history_dir
    return Path(directory).resolve() / f"{holding_id}.md"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _render_summary(
    *,
    holding: orm.Holding,
    thesis: orm.Thesis,
    versions: list[orm.ThesisVersion],
    analyses: list[orm.AnalysisResult],
    evidence_rows: list[orm.Evidence],
    max_items: int,
) -> tuple[str, list[str], list[str]]:
    # Exclusion must consider the complete DB history, not only the entries shown
    # in the capped narrative file.
    document_ids = list(dict.fromkeys(row.document_id for row in evidence_rows))
    source_urls = list(
        dict.fromkeys(str(row.source_url) for row in evidence_rows if row.source_url)
    )
    unique_evidence = select_substantive_evidence(evidence_rows, max_items=max_items)

    analyses_by_version = {
        row.thesis_version_id: row for row in analyses if row.thesis_version_id is not None
    }
    latest_version = versions[-1] if versions else None
    support = [row for row in unique_evidence if _enum_value(row.classification) == "SUPPORT"][-3:]
    contradict = [
        row for row in unique_evidence if _enum_value(row.classification) == "CONTRADICT"
    ][-3:]

    lines = [
        f"# {holding.ticker} 근거 히스토리",
        "",
        "> 역할: 종목 스토리 파악을 위한 서사 문맥 전용입니다.",
        "> 점수 규칙: 아래 과거 근거는 현재 신뢰도와 상태에 이미 반영되었으므로",
        "> 분류 강도·영향도·신뢰도·상태 변화에 직접 다시 반영하면 안 됩니다.",
        "",
        "## 현재 투자 논리",
        "",
        f"- 핵심 논리: {_one_line(thesis.main_thesis)}",
        f"- 핵심 가정: {_one_line(' / '.join(thesis.key_assumptions))}",
        f"- 현재 기준점: 신뢰도 {thesis.confidence_score}, 상태 {_enum_value(thesis.status)}",
        "",
        "## 누적 스토리 요약",
        "",
    ]
    if support:
        lines.append(
            "- 이어진 지지 흐름: "
            + " / ".join(_one_line(row.content_snippet, max_length=220) for row in support)
        )
    else:
        lines.append("- 이어진 지지 흐름: 저장된 방향성 지지 근거 없음")
    if contradict:
        lines.append(
            "- 이어진 반박 흐름: "
            + " / ".join(_one_line(row.content_snippet, max_length=220) for row in contradict)
        )
    else:
        lines.append("- 이어진 반박 흐름: 저장된 방향성 반박 근거 없음")
    if latest_version is not None:
        lines.extend(
            [
                "- 최근 판단: " + _one_line(latest_version.change_reason, max_length=400),
                "- 미해결 충돌 가정: "
                + (_one_line(" / ".join(latest_version.conflicting_assumptions)) or "없음"),
                "- 다음 관찰 지점: "
                + (_one_line(" / ".join(latest_version.observation_points)) or "없음"),
            ]
        )
    else:
        lines.append("- 최근 판단: 아직 저장된 분석 이력이 없음")

    lines.extend(["", "## 판단 흐름", ""])
    if not versions:
        lines.append("- 저장된 판단 이력이 없습니다.")
    for version in versions[-10:]:
        analysis = analyses_by_version.get(version.id)
        lines.append(
            f"- v{version.version_no} | {_date(version.created_at)} | "
            f"신뢰도 {version.confidence_score} | {_enum_value(version.status)} | "
            f"{_one_line(version.change_reason, max_length=350)}"
        )
        if analysis is not None and analysis.judge_summary:
            lines.append(f"  - Judge: {_one_line(analysis.judge_summary, max_length=450)}")

    lines.extend(["", "## 고유 근거 타임라인", ""])
    if not unique_evidence:
        lines.append("- 저장된 과거 근거가 없습니다.")
    for row in unique_evidence:
        assumptions = _one_line(" / ".join(row.related_assumptions)) or "연결 가정 미기록"
        lines.extend(
            [
                f"- {_date(row.published_at or row.created_at)} | "
                f"{_enum_value(row.classification)}/{_enum_value(row.impact)} | "
                f"document_id={_one_line(row.document_id, max_length=350)}",
                f"  - 연결 가정: {assumptions}",
                f"  - 요약: {_one_line(row.content_snippet, max_length=500)}",
                f"  - 당시 판단 이유: {_one_line(row.reason, max_length=400)}",
            ]
        )

    lines.extend(
        [
            "",
            "## 새 정보 판단 규칙",
            "",
            "- 이 파일은 현재 종목의 인과적 스토리를 이해하는 데만 사용합니다.",
            "- 새 정보가 과거 흐름을 이어가거나 뒤집거나 구체화하는지 설명합니다.",
            "- 과거 사실 자체에는 신규 점수 영향을 부여하지 않습니다.",
            "- 동일 사실의 반복은 0의 추가 영향으로 처리하고, 새로 추가된 변화분만 판단합니다.",
            "",
            f"갱신 시각: {_date(datetime.now(UTC))}",
            "",
        ]
    )
    return "\n".join(lines), document_ids, source_urls


async def refresh_evidence_history_file(
    session: AsyncSession,
    *,
    holding: orm.Holding,
    thesis: orm.Thesis,
    history_dir: Path | None = None,
    max_items: int | None = None,
) -> EvidenceHistorySnapshot:
    settings = get_settings()
    versions = list(
        await session.scalars(
            select(orm.ThesisVersion)
            .where(orm.ThesisVersion.thesis_id == thesis.id)
            .order_by(orm.ThesisVersion.version_no.asc())
        )
    )
    analyses = list(
        await session.scalars(
            select(orm.AnalysisResult)
            .where(
                orm.AnalysisResult.thesis_id == thesis.id,
                orm.AnalysisResult.analysis_type == orm.AnalysisType.BULL_BEAR_JUDGE,
            )
            .order_by(orm.AnalysisResult.created_at.asc())
        )
    )
    evidence_rows = list(
        await session.scalars(
            select(orm.Evidence)
            .where(
                orm.Evidence.thesis_id == thesis.id,
                orm.Evidence.saved_to_history.is_(True),
            )
            .order_by(orm.Evidence.created_at.asc())
        )
    )
    summary, document_ids, source_urls = _render_summary(
        holding=holding,
        thesis=thesis,
        versions=versions,
        analyses=analyses,
        evidence_rows=evidence_rows,
        max_items=max_items or settings.evidence_history_max_items,
    )
    path = _history_path(holding.id, history_dir)
    await asyncio.to_thread(_atomic_write, path, summary)
    return EvidenceHistorySnapshot(
        summary=summary,
        document_ids=document_ids,
        source_urls=source_urls,
        path=path,
    )


async def clear_evidence_history(
    session: AsyncSession,
    *,
    holding: orm.Holding,
    thesis: orm.Thesis,
    history_dir: Path | None = None,
) -> None:
    """Explicitly clear saved evidence and its derived context for one thesis.

    This is a destructive user-level operation, not analysis-run setup. Normal
    reanalysis must preserve history; thesis logic edits use
    ``reset_evidence_for_logic_change`` instead.
    """

    await session.execute(
        update(orm.Evidence)
        .where(
            orm.Evidence.thesis_id == thesis.id,
            orm.Evidence.saved_to_history.is_(True),
        )
        .values(saved_to_history=False)
    )
    # The analysis workflow opens its own session, so the reset must be
    # committed before it starts and loads the materialized history file.
    await session.commit()
    await asyncio.to_thread(_history_path(holding.id, history_dir).unlink, missing_ok=True)


async def reset_evidence_for_logic_change(
    session: AsyncSession,
    *,
    holding: orm.Holding,
    thesis: orm.Thesis,
    history_dir: Path | None = None,
) -> None:
    """Remove evidence assessed against a superseded thesis logic graph."""

    await session.execute(delete(orm.Evidence).where(orm.Evidence.thesis_id == thesis.id))
    await session.commit()
    await delete_thesis_evidence_vectors(thesis.id)
    await asyncio.to_thread(_history_path(holding.id, history_dir).unlink, missing_ok=True)


async def refresh_all_evidence_history_files(
    session_factory: async_sessionmaker,
    *,
    history_dir: Path | None = None,
) -> None:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(orm.Holding, orm.Thesis).join(
                    orm.Thesis, orm.Thesis.holding_id == orm.Holding.id
                )
            )
        ).all()
        for holding, thesis in rows:
            await refresh_evidence_history_file(
                session,
                holding=holding,
                thesis=thesis,
                history_dir=history_dir,
            )
