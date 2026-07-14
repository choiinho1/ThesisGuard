"use client";

import { useEffect, useState } from "react";
import { getThesisHistory } from "@/lib/apiClient";
import { StatusBadge } from "@/components/StatusBadge";
import type { ApiMode, DashboardHolding, Evidence, ThesisVersion } from "@/types/schema";

interface SavedEvidenceEntry {
  evidence: Evidence;
  holdingId: string;
  ticker: string;
}

interface ConfidenceEntry {
  holdingId: string;
  ticker: string;
  version: ThesisVersion;
}

export function SavedEvidenceHistory({ holdings, mode }: { holdings: DashboardHolding[]; mode: ApiMode }) {
  const [entries, setEntries] = useState<SavedEvidenceEntry[]>([]);
  const [confidenceEntries, setConfidenceEntries] = useState<ConfidenceEntry[]>([]);
  const [loadingConfidence, setLoadingConfidence] = useState(true);
  const [selectedHoldingId, setSelectedHoldingId] = useState(() => holdings[0]?.id ?? "");
  const activeHoldingId = holdings.some((holding) => holding.id === selectedHoldingId)
    ? selectedHoldingId
    : holdings[0]?.id ?? "";
  const activeHolding = holdings.find((holding) => holding.id === activeHoldingId) ?? null;
  const visibleEntries = entries.filter((entry) => entry.holdingId === activeHoldingId);
  const visibleConfidenceEntries = confidenceEntries.filter(
    (entry) => entry.holdingId === activeHoldingId,
  );

  useEffect(() => {
    const restored = holdings.flatMap((holding) => {
      const raw = window.localStorage.getItem(`thesisguard_saved_evidence_${holding.id}`);
      if (!raw) return [];
      try {
        return (JSON.parse(raw) as Evidence[]).map((evidence) => ({
          evidence,
          holdingId: holding.id,
          ticker: holding.ticker,
        }));
      } catch {
        return [];
      }
    }).sort((left, right) => (
      new Date(right.evidence.created_at).getTime() - new Date(left.evidence.created_at).getTime()
    ));
    const timer = window.setTimeout(() => setEntries(restored), 0);
    return () => window.clearTimeout(timer);
  }, [holdings]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all(holdings.filter((holding) => holding.thesis).map(async (holding) => {
      const versions = await getThesisHistory(holding.thesis!.id, mode);
      return versions
        .filter((version) => version.confidence_score !== version.snapshot.confidence_score)
        .map((version) => ({ holdingId: holding.id, ticker: holding.ticker, version }));
    })).then((groups) => {
      if (!cancelled) {
        setConfidenceEntries(groups.flat().sort((left, right) =>
          new Date(right.version.created_at).getTime() - new Date(left.version.created_at).getTime()));
      }
    }).catch(() => {
      if (!cancelled) setConfidenceEntries([]);
    }).finally(() => {
      if (!cancelled) setLoadingConfidence(false);
    });
    return () => { cancelled = true; };
  }, [holdings, mode]);

  const removeEntry = (entry: SavedEvidenceEntry) => {
    const key = `thesisguard_saved_evidence_${entry.holdingId}`;
    const nextEntries = entries.filter((item) => item.evidence.id !== entry.evidence.id);
    const remainingForHolding = nextEntries
      .filter((item) => item.holdingId === entry.holdingId)
      .map((item) => item.evidence);
    window.localStorage.setItem(key, JSON.stringify(remainingForHolding));
    setEntries(nextEntries);
  };

  const removeAllVisibleEntries = () => {
    if (!activeHolding || visibleEntries.length === 0) return;
    if (!window.confirm(`${activeHolding.ticker}의 저장 근거를 모두 삭제할까요?`)) return;
    window.localStorage.removeItem(`thesisguard_saved_evidence_${activeHolding.id}`);
    setEntries((current) => current.filter((entry) => entry.holdingId !== activeHolding.id));
  };

  return (
    <div className="history-sections">
    <section className="history-holding-filter" aria-label="History 종목 선택">
      <div>
        <span className="kicker">SELECT HOLDING</span>
        <strong>{activeHolding ? `${activeHolding.ticker} History` : "종목을 선택하세요"}</strong>
      </div>
      <div className="history-holding-tabs">
        {holdings.map((holding) => (
          <button
            aria-pressed={holding.id === activeHoldingId}
            className={holding.id === activeHoldingId ? "is-active" : ""}
            key={holding.id}
            onClick={() => setSelectedHoldingId(holding.id)}
            type="button"
          >
            {holding.ticker}
          </button>
        ))}
      </div>
    </section>

    <section className="panel evidence-history-panel">
      <div className="evidence-history-heading">
        <div>
          <span className="section-index">05</span>
          <p className="kicker">CONFIDENCE HISTORY</p>
          <h2>Confidence 변경 이력</h2>
          <p>분석으로 점수가 변경된 시점의 판단과 근거를 기록합니다.</p>
        </div>
        <span className="history-count">{visibleConfidenceEntries.length} CHANGES</span>
      </div>
      {loadingConfidence ? (
        <div className="history-empty"><strong>변경 이력을 불러오는 중…</strong></div>
      ) : visibleConfidenceEntries.length === 0 ? (
        <div className="history-empty"><strong>{activeHolding?.ticker ?? "선택 종목"}의 confidence 변경 이력이 없습니다.</strong><p>종목을 재분석하면 결과가 여기에 저장됩니다.</p></div>
      ) : (
        <div className="confidence-history-list scrollable-list" role="region" aria-label="Confidence 변경 이력 목록" tabIndex={0}>
          {visibleConfidenceEntries.map(({ ticker, version }) => (
            <article key={version.id}>
              <div className="history-meta">
                <span className="history-ticker">{ticker}</span>
                <StatusBadge status={version.status} />
                <time>{new Date(version.created_at).toLocaleString("ko-KR")}</time>
              </div>
              <div className="confidence-change">
                <span>{version.snapshot.confidence_score}</span><b>→</b><strong>{version.confidence_score}</strong>
                <small>{version.confidence_score - version.snapshot.confidence_score >= 0 ? "+" : ""}{version.confidence_score - version.snapshot.confidence_score}점</small>
              </div>
              <p><strong>판단 근거</strong>{version.change_reason}</p>
              {version.conflicting_assumptions.length > 0 && <p><strong>충돌 전제</strong>{version.conflicting_assumptions.join(" · ")}</p>}
            </article>
          ))}
        </div>
      )}
    </section>

    <section className="panel evidence-history-panel">
      <div className="evidence-history-heading">
        <div>
          <span className="section-index">05</span>
          <p className="kicker">SAVED EVIDENCE</p>
          <h2>주요 근거 History</h2>
          <p>분석 과정에서 직접 저장한 근거만 시간순으로 모았습니다.</p>
        </div>
        <div className="history-heading-actions">
          <span className="history-count">{visibleEntries.length} SAVED</span>
          <button disabled={visibleEntries.length === 0} onClick={removeAllVisibleEntries} type="button">전체 삭제</button>
        </div>
      </div>

      {visibleEntries.length === 0 ? (
        <div className="history-empty">
          <strong>{activeHolding?.ticker ?? "선택 종목"}에 저장한 근거가 없습니다.</strong>
          <p>Main의 분석 결과에서 `주요 근거로 저장`을 선택해 보세요.</p>
        </div>
      ) : (
        <div className="evidence-history-list scrollable-list" role="region" aria-label="저장 근거 이력 목록" tabIndex={0}>
          {visibleEntries.map((entry) => (
            <article key={`${entry.holdingId}-${entry.evidence.id}`}>
              <div className="history-meta">
                <span className="history-ticker">{entry.ticker}</span>
                <span>{entry.evidence.classification} · {entry.evidence.impact}</span>
                <time>{new Date(entry.evidence.created_at).toLocaleString("ko-KR")}</time>
              </div>
              <p>{entry.evidence.content_snippet}</p>
              <div className="history-actions">
                {entry.evidence.source_url && (
                  <a href={entry.evidence.source_url} rel="noreferrer" target="_blank">원문 보기 ↗</a>
                )}
                <button onClick={() => removeEntry(entry)} type="button">History에서 삭제</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
    </div>
  );
}
