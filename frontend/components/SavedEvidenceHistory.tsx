"use client";

import { useEffect, useState } from "react";
import type { DashboardHolding, Evidence } from "@/types/schema";

interface SavedEvidenceEntry {
  evidence: Evidence;
  holdingId: string;
  ticker: string;
}

export function SavedEvidenceHistory({ holdings }: { holdings: DashboardHolding[] }) {
  const [entries, setEntries] = useState<SavedEvidenceEntry[]>([]);

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

  const removeEntry = (entry: SavedEvidenceEntry) => {
    const key = `thesisguard_saved_evidence_${entry.holdingId}`;
    const nextEntries = entries.filter((item) => item.evidence.id !== entry.evidence.id);
    const remainingForHolding = nextEntries
      .filter((item) => item.holdingId === entry.holdingId)
      .map((item) => item.evidence);
    window.localStorage.setItem(key, JSON.stringify(remainingForHolding));
    setEntries(nextEntries);
  };

  return (
    <section className="panel evidence-history-panel">
      <div className="evidence-history-heading">
        <div>
          <span className="section-index">05</span>
          <p className="kicker">SAVED EVIDENCE</p>
          <h2>주요 근거 History</h2>
          <p>분석 과정에서 직접 저장한 근거만 시간순으로 모았습니다.</p>
        </div>
        <span className="history-count">{entries.length} SAVED</span>
      </div>

      {entries.length === 0 ? (
        <div className="history-empty">
          <strong>아직 저장한 근거가 없습니다.</strong>
          <p>Main의 분석 결과에서 `주요 근거로 저장`을 선택해 보세요.</p>
        </div>
      ) : (
        <div className="evidence-history-list">
          {entries.map((entry) => (
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
  );
}
