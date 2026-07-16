"use client";

import { useEffect, useState } from "react";
import { CausalLogicGraph } from "@/components/CausalLogicGraph";
import { StatusBadge } from "@/components/StatusBadge";
import { saveEvidenceToHistory } from "@/lib/apiClient";
import type {
  ApiMode,
  DashboardHolding,
  Evidence,
  HoldingAnalysisResponse,
} from "@/types/schema";

function finiteNumber(value: number | null | undefined, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

interface ThesisDetailProps {
  holding: DashboardHolding;
  analysis: HoldingAnalysisResponse | null;
  analyzing: boolean;
  mode: ApiMode;
  onAnalyze: () => void;
  onRegister: (rawInput: string) => Promise<void>;
  onUpdate: (rawInput: string) => Promise<void>;
}

export function ThesisDetail({
  holding,
  analysis,
  analyzing,
  mode,
  onAnalyze,
  onRegister,
  onUpdate,
}: ThesisDetailProps) {
  const [rawInput, setRawInput] = useState("");
  const [registering, setRegistering] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editInput, setEditInput] = useState(holding.thesis?.raw_input ?? "");
  const [savingEdit, setSavingEdit] = useState(false);
  const [savedEvidenceIds, setSavedEvidenceIds] = useState<Set<string>>(new Set());
  const [savingEvidenceIds, setSavingEvidenceIds] = useState<Set<string>>(new Set());
  const [evidenceSaveError, setEvidenceSaveError] = useState<string | null>(null);
  const thesis = analysis?.thesis ?? holding.thesis;
  const thesisLength = rawInput.trim().length;
  const byAbsoluteScoreImpact = (left: Evidence, right: Evidence) => {
    const leftDelta = finiteNumber(left.score_delta);
    const rightDelta = finiteNumber(right.score_delta);
    return Math.abs(rightDelta) - Math.abs(leftDelta) || rightDelta - leftDelta;
  };
  const pastEvidence = analysis?.evidence
    .filter((evidence) => evidence.evidence_scope === "PAST")
    .sort(byAbsoluteScoreImpact) ?? [];
  const newEvidence = analysis?.evidence
    .filter((evidence) => evidence.evidence_scope === "NEW")
    .sort(byAbsoluteScoreImpact) ?? [];
  const emptyEvidenceMessage = "새로운 고유 근거가 없습니다. 과거 근거는 아래에서 확인하세요.";

  useEffect(() => {
    if (mode === "live") {
      const ids = new Set(
        analysis?.evidence
          .filter((evidence) => evidence.saved_to_history)
          .map((evidence) => evidence.id) ?? [],
      );
      const timer = window.setTimeout(() => setSavedEvidenceIds(ids), 0);
      return () => window.clearTimeout(timer);
    }

    const stored = window.localStorage.getItem(`thesisguard_saved_evidence_${holding.id}`);
    let restored: Evidence[] = [];
    try {
      restored = stored ? JSON.parse(stored) as Evidence[] : [];
    } catch {
      restored = [];
    }
    const timer = window.setTimeout(
      () => setSavedEvidenceIds(new Set(restored.map((evidence) => evidence.id))),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [analysis, holding.id, mode]);

  useEffect(() => {
    if (mode !== "mock" || !analysis) return;
    const automaticallySaved = analysis.evidence.filter(
      (evidence) => evidence.impact === "HIGH" || evidence.impact === "MEDIUM",
    );
    if (automaticallySaved.length === 0) return;

    const timer = window.setTimeout(() => {
      setSavedEvidenceIds((current) => {
        const nextIds = new Set(current);
        automaticallySaved.forEach((evidence) => nextIds.add(evidence.id));
        window.localStorage.setItem(
          `thesisguard_saved_evidence_${holding.id}`,
          JSON.stringify(analysis.evidence
            .filter((evidence) => nextIds.has(evidence.id))
            .map((evidence) => ({ ...evidence, saved_to_history: true }))),
        );
        return nextIds;
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [analysis, holding.id, mode]);

  const toggleSavedEvidence = async (evidence: Evidence) => {
    if (savingEvidenceIds.has(evidence.id) || savedEvidenceIds.has(evidence.id)) return;
    setEvidenceSaveError(null);
    setSavingEvidenceIds((current) => new Set(current).add(evidence.id));
    try {
      await saveEvidenceToHistory(evidence, mode);
      const nextIds = new Set(savedEvidenceIds);
      nextIds.add(evidence.id);
      setSavedEvidenceIds(nextIds);

      if (mode === "mock" && analysis) {
        window.localStorage.setItem(
          `thesisguard_saved_evidence_${holding.id}`,
          JSON.stringify(analysis.evidence
            .filter((item) => nextIds.has(item.id))
            .map((item) => ({ ...item, saved_to_history: true }))),
        );
      }
    } catch (error) {
      setEvidenceSaveError(error instanceof Error ? error.message : "근거 저장 상태를 변경하지 못했습니다.");
    } finally {
      setSavingEvidenceIds((current) => {
        const next = new Set(current);
        next.delete(evidence.id);
        return next;
      });
    }
  };

  if (!thesis) {
    return (
      <section className="panel thesis-detail empty-thesis">
        <span className="section-index">04</span>
        <h2>{holding.ticker} Thesis</h2>
        <p>매수 이유를 자연어로 입력하면 핵심 전제·신호·리스크로 구조화합니다.</p>
        <textarea
          aria-label="투자 논리 원문"
          onChange={(event) => setRawInput(event.target.value)}
          placeholder="예: AI 반도체 수요 증가와 소프트웨어 경쟁력을 바탕으로 장기 성장할 것이다."
          value={rawInput}
        />
        <p className={`input-guidance ${thesisLength > 0 && thesisLength < 10 ? "is-error" : ""}`}>
          {thesisLength < 10
            ? `투자 논리를 등록하려면 ${10 - thesisLength}자를 더 입력하세요.`
            : `투자 논리 ${thesisLength}자 · ${holding.ticker}에 등록됩니다.`}
        </p>
        <button
          className="primary-button"
          disabled={registering || thesisLength < 10}
          onClick={async () => {
            setRegistering(true);
            try {
              await onRegister(rawInput.trim());
            } finally {
              setRegistering(false);
            }
          }}
          type="button"
        >
          {registering ? "Thesis 구조화 중…" : "투자 논리 등록"}
        </button>
      </section>
    );
  }

  return (
    <section className="panel thesis-detail">
      <div className="thesis-title-row">
        <div>
          <span className="section-index">04</span>
          <p className="kicker">{holding.ticker} / CURRENT THESIS</p>
          <h2>{thesis.main_thesis}</h2>
        </div>
        <div className="confidence-hero">
          <span>CONFIDENCE</span>
          <strong>{thesis.confidence_score}</strong>
          <StatusBadge status={thesis.status} />
        </div>
      </div>

      <div className="thesis-grid">
        <DetailList title="핵심 전제" items={thesis.key_assumptions} />
        <DetailList title="긍정 신호" items={thesis.positive_signals} tone="positive" />
        <DetailList title="부정 신호" items={thesis.negative_signals} tone="negative" />
        <DetailList title="주요 리스크" items={thesis.key_risks} tone="risk" />
      </div>

      {thesis.logic_graph && thesis.score_breakdown && thesis.score_breakdown.node_scores.length > 0 && (
        <CausalLogicGraph graph={thesis.logic_graph} scoreBreakdown={thesis.score_breakdown} />
      )}

      {editing && (
        <section className="thesis-editor">
          <label htmlFor={`edit-thesis-${holding.id}`}>투자 논리 수정</label>
          <textarea
            id={`edit-thesis-${holding.id}`}
            onChange={(event) => setEditInput(event.target.value)}
            value={editInput}
          />
          <p className={`input-guidance ${editInput.trim().length > 0 && editInput.trim().length < 10 ? "is-error" : ""}`}>
            {editInput.trim().length < 10
              ? `${10 - editInput.trim().length}자를 더 입력하세요.`
              : "저장 후 최신 근거로 자동 재분석하며 점수가 갱신됩니다."}
          </p>
          <div className="thesis-editor-actions">
            <button className="secondary-button" disabled={savingEdit} onClick={() => { setEditInput(thesis.raw_input); setEditing(false); }} type="button">취소</button>
            <button
              className="primary-button"
              disabled={savingEdit || analyzing || editInput.trim().length < 10 || editInput.trim() === thesis.raw_input.trim()}
              onClick={async () => {
                setSavingEdit(true);
                try {
                  await onUpdate(editInput.trim());
                  setEditing(false);
                } finally {
                  setSavingEdit(false);
                }
              }}
              type="button"
            >
              {savingEdit ? "저장·재분석 중…" : "저장 후 재분석"}
            </button>
          </div>
        </section>
      )}

      {analyzing && <AnalysisProgress />}

      {analysis && (
        <div className="analysis-result">
          <div className="analysis-summary-grid">
            <section className="analysis-card analysis-card--judge">
              <div className="analysis-card-heading">
                <span className="result-label">종합 판단</span>
                <strong className="judge-score" aria-label={`최종 점수 ${analysis.thesis.confidence_score}점`}>
                  {analysis.thesis.confidence_score}<small>/±50</small>
                </strong>
              </div>
              <p>{analysis.analysis_result.judge_summary}</p>
            </section>

            <section className="analysis-card analysis-card--changes">
              <span className="result-label">달라진 점</span>
              <p>{analysis.version.change_reason}</p>
            </section>
          </div>

          <details className="analysis-evidence" open>
            <summary>
              <span><span className="result-label">NEW</span> 새 근거</span>
              <span className="evidence-count">{newEvidence.length}</span>
            </summary>
            <div className="evidence-list scrollable-list" role="region" aria-label="분석 근거 목록" tabIndex={0}>
              {newEvidence.map((evidence) => (
                <EvidenceRow
                  evidence={evidence}
                  isSaved={savedEvidenceIds.has(evidence.id)}
                  isSaving={savingEvidenceIds.has(evidence.id)}
                  key={evidence.id}
                  onToggleSaved={toggleSavedEvidence}
                />
              ))}
              {newEvidence.length === 0 && (
                <p className="empty-copy">{emptyEvidenceMessage}</p>
              )}
            </div>
          </details>

          {pastEvidence.length > 0 && (
            <details className="analysis-evidence past-evidence">
              <summary>
                <span><span className="result-label">PAST</span> 과거 근거</span>
                <span className="evidence-count">{pastEvidence.length}</span>
              </summary>
              <div
                aria-label="과거 분석 근거 목록"
                className="evidence-list scrollable-list"
                role="region"
                tabIndex={0}
              >
                {pastEvidence.map((evidence) => (
                  <EvidenceRow
                    evidence={evidence}
                    isSaved={savedEvidenceIds.has(evidence.id)}
                    isSaving={savingEvidenceIds.has(evidence.id)}
                    key={evidence.id}
                    onToggleSaved={toggleSavedEvidence}
                  />
                ))}
              </div>
            </details>
          )}
          {evidenceSaveError && <p className="error-banner" role="alert">{evidenceSaveError}</p>}
        </div>
      )}

      <div className="thesis-actions">
        <p>모든 분석 결과는 근거 URL과 원문 발췌를 동반합니다.</p>
        <div className="thesis-action-buttons">
          <button className="secondary-button" disabled={analyzing} onClick={() => { setEditInput(thesis.raw_input); setEditing((current) => !current); }} type="button">
            {editing ? "수정 닫기" : "투자 논리 수정"}
          </button>
          <button className="primary-button" disabled={analyzing} onClick={onAnalyze} type="button">
            {analyzing ? "분석 파이프라인 실행 중…" : "새 정보로 재분석"}
          </button>
        </div>
      </div>
    </section>
  );
}

interface EvidenceRowProps {
  evidence: Evidence;
  isSaved: boolean;
  isSaving: boolean;
  onToggleSaved: (evidence: Evidence) => void;
}

function EvidenceRow({ evidence, isSaved, isSaving, onToggleSaved }: EvidenceRowProps) {
  const scoreDelta = finiteNumber(evidence.score_delta);
  const directionalNodes = (evidence.node_contributions ?? []).filter(
    (contribution) => finiteNumber(contribution.signed_strength) !== 0,
  );
  return (
    <article className="evidence-link evidence-link--static">
      <div className="evidence-meta">
        <span>{evidence.classification} · {evidence.impact}</span>
        <strong className={
          scoreDelta > 0
            ? "evidence-score-impact positive"
            : scoreDelta < 0
              ? "evidence-score-impact negative"
              : "evidence-score-impact"
        }>
          최종 점수 {scoreDelta > 0 ? "+" : ""}{scoreDelta.toFixed(2)}
        </strong>
        {evidence.published_at ? (
          <time dateTime={evidence.published_at}>
            {formatEvidenceDate(evidence.published_at)}
          </time>
        ) : (
          <span className="evidence-date">날짜 정보 없음</span>
        )}
      </div>
      <p>{evidence.content_snippet}</p>
      {directionalNodes.length > 0 && (
        <details className="evidence-node-contributions">
          <summary>가정 노드별 기여도 {directionalNodes.length}개</summary>
          <ul>
            {directionalNodes.map((contribution) => (
              <li key={contribution.node_id}>
                <span>{contribution.assumption}</span>
                <strong
                  className={finiteNumber(contribution.signed_strength) > 0 ? "positive" : "negative"}
                >
                  {finiteNumber(contribution.signed_strength) > 0 ? "+" : ""}
                  {finiteNumber(contribution.signed_strength).toFixed(2)}
                </strong>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="evidence-actions">
        {evidence.source_url && (
          <a
            className="evidence-source-link"
            href={evidence.source_url}
            rel="noreferrer"
            target="_blank"
          >
            원문 보기 ↗
          </a>
        )}
        <button
          className={isSaved ? "evidence-save-button is-saved" : "evidence-save-button"}
          disabled={isSaving || isSaved}
          onClick={() => onToggleSaved(evidence)}
          type="button"
        >
          {isSaving
            ? "처리 중…"
            : isSaved
              ? "저장됨"
              : "주요 근거로 저장"}
        </button>
      </div>
    </article>
  );
}

function formatEvidenceDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "날짜 정보 없음";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Seoul",
  }).format(date);
}

function AnalysisProgress() {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = performance.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds((performance.now() - startedAt) / 1000);
    }, 250);
    return () => window.clearInterval(timer);
  }, []);

  const progress = Math.min(94, Math.max(3, Math.round(100 * (1 - Math.exp(-elapsedSeconds / 35)))));
  const phase = progress < 25
    ? "시장 자료 수집"
    : progress < 55
      ? "근거 분류"
      : progress < 80
        ? "찬반 논리 검토"
        : "최종 판단 정리";

  return (
    <section className="analysis-progress" aria-label={`분석 예상 진행률 ${progress}%`} aria-live="polite">
      <div className="analysis-progress-heading">
        <div>
          <span className="result-label">ANALYZING</span>
          <strong>{phase}</strong>
        </div>
        <div className="analysis-progress-value">
          <strong>{progress}%</strong>
          <span>{Math.floor(elapsedSeconds)}초 경과</span>
        </div>
      </div>
      <div
        className="analysis-progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <p>실제 소요 시간은 종목과 근거 수에 따라 달라질 수 있습니다.</p>
    </section>
  );
}

function DetailList({
  title,
  items,
  tone = "default",
}: {
  title: string;
  items: string[];
  tone?: "default" | "positive" | "negative" | "risk";
}) {
  return (
    <div className={`detail-list detail-list--${tone}`}>
      <h3>{title}</h3>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}
