"use client";

import { useMemo, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import type { DashboardHolding } from "@/types/schema";

type SortKey = "weight" | "name" | "score";

export function HoldingGrid({
  holdings,
  selectedId,
  onSelect,
  onDelete,
}: {
  holdings: DashboardHolding[];
  selectedId: string | null;
  onSelect: (holding: DashboardHolding) => void;
  onDelete: (holding: DashboardHolding) => Promise<void>;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("weight");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const sortedHoldings = useMemo(() => [...holdings].sort((left, right) => {
    if (sortKey === "name") {
      return (left.company_name || left.ticker).localeCompare(
        right.company_name || right.ticker,
        "ko-KR",
      );
    }
    if (sortKey === "score") {
      return (right.thesis?.confidence_score ?? -1) - (left.thesis?.confidence_score ?? -1);
    }
    return right.current_weight - left.current_weight;
  }), [holdings, sortKey]);

  const requestDelete = async (holding: DashboardHolding) => {
    if (!window.confirm(`${holding.ticker}를 포트폴리오에서 삭제할까요? 관련 Thesis와 분석 기록도 함께 삭제됩니다.`)) return;
    setDeletingId(holding.id);
    try {
      await onDelete(holding);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="panel holdings-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">02</span>
          <h2>Thesis Monitor</h2>
        </div>
        <div className="holding-heading-actions">
          <label className="sort-control">
            <span>정렬</span>
            <select onChange={(event) => setSortKey(event.target.value as SortKey)} value={sortKey}>
              <option value="weight">비중순</option>
              <option value="name">이름순</option>
              <option value="score">점수순</option>
            </select>
          </label>
          <span className="panel-meta">{holdings.length} HOLDINGS</span>
        </div>
      </div>
      <div className="holding-table">
        {sortedHoldings.map((holding) => (
          <div className="holding-item" key={holding.id}>
            <button
              className={`holding-row ${selectedId === holding.id ? "is-selected" : ""}`}
              onClick={() => onSelect(holding)}
              type="button"
            >
              <span className="ticker-cell">
                <strong>{holding.ticker}</strong>
                <small>{holding.company_name}</small>
              </span>
              <span className="weight-cell">
                <small>현재 / 목표</small>
                <strong>{holding.current_weight}% / {holding.target_weight}%</strong>
              </span>
              <span className="confidence-cell">
                <small>Confidence</small>
                <strong>{holding.thesis?.confidence_score ?? "--"}</strong>
              </span>
              <span>
                {holding.thesis ? <StatusBadge status={holding.thesis.status} /> : <span className="status">미등록</span>}
              </span>
            </button>
            <button
              aria-label={`${holding.ticker} 삭제`}
              className="holding-delete"
              disabled={deletingId === holding.id}
              onClick={() => { void requestDelete(holding); }}
              title="보유 종목 삭제"
              type="button"
            >
              {deletingId === holding.id ? "…" : "삭제"}
            </button>
          </div>
        ))}
        {sortedHoldings.length === 0 && <p className="empty-copy holding-empty">등록된 보유 종목이 없습니다.</p>}
      </div>
    </section>
  );
}
