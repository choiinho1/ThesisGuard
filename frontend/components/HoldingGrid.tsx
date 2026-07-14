"use client";

import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { StatusBadge } from "@/components/StatusBadge";
import type {
  DashboardHolding,
  MarketSnapshot,
  UpdateHoldingPositionInput,
} from "@/types/schema";

type SortKey = "weight" | "name" | "score";

interface FloatingMarket {
  holding: DashboardHolding;
  left: number;
  top: number;
}

export function HoldingGrid({
  holdings,
  selectedId,
  onSelect,
  onDelete,
  onUpdatePosition,
  onLoadMarketSnapshot,
}: {
  holdings: DashboardHolding[];
  selectedId: string | null;
  onSelect: (holding: DashboardHolding) => void;
  onDelete: (holding: DashboardHolding) => Promise<void>;
  onUpdatePosition: (
    holding: DashboardHolding,
    input: UpdateHoldingPositionInput,
  ) => Promise<void>;
  onLoadMarketSnapshot: (holding: DashboardHolding) => Promise<MarketSnapshot>;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("weight");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [updatingPositionId, setUpdatingPositionId] = useState<string | null>(null);
  const [editingPositionId, setEditingPositionId] = useState<string | null>(null);
  const [positionDraft, setPositionDraft] = useState({ quantity: "", current: "", target: "" });
  const [marketSnapshots, setMarketSnapshots] = useState<Record<string, MarketSnapshot>>({});
  const [loadingMarketId, setLoadingMarketId] = useState<string | null>(null);
  const [floatingMarket, setFloatingMarket] = useState<FloatingMarket | null>(null);

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

  const openPositionEditor = (holding: DashboardHolding) => {
    setEditingPositionId(holding.id);
    setPositionDraft({
      quantity: String(holding.quantity),
      current: String(holding.current_weight),
      target: String(holding.target_weight),
    });
  };

  const savePosition = async (holding: DashboardHolding) => {
    const input = {
      quantity: Number(positionDraft.quantity),
      current_weight: Number(positionDraft.current),
      target_weight: Number(positionDraft.target),
    };
    const valid = Number.isFinite(input.quantity) && input.quantity >= 0
      && Number.isFinite(input.current_weight) && input.current_weight >= 0
      && input.current_weight <= 100
      && Number.isFinite(input.target_weight) && input.target_weight >= 0
      && input.target_weight <= 100;
    if (!valid) {
      window.alert("수량은 0 이상, 비중은 0에서 100 사이로 입력해 주세요.");
      return;
    }
    setUpdatingPositionId(holding.id);
    try {
      await onUpdatePosition(holding, input);
      setEditingPositionId(null);
    } finally {
      setUpdatingPositionId(null);
    }
  };

  const loadMarketSnapshot = async (holding: DashboardHolding) => {
    if (marketSnapshots[holding.id] || loadingMarketId === holding.id) return;
    setLoadingMarketId(holding.id);
    try {
      const snapshot = await onLoadMarketSnapshot(holding);
      setMarketSnapshots((current) => ({ ...current, [holding.id]: snapshot }));
    } finally {
      setLoadingMarketId(null);
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
      <div className="holding-table scrollable-list" onScroll={() => setFloatingMarket(null)} role="region" aria-label="보유 종목 목록" tabIndex={0}>
        {sortedHoldings.map((holding) => (
          <div className="holding-item" key={holding.id}>
            <button
              className={`holding-row ${selectedId === holding.id ? "is-selected" : ""}`}
              onClick={() => onSelect(holding)}
              type="button"
            >
              <span
                className="ticker-cell ticker-hover"
                onMouseEnter={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  const tooltipWidth = 280;
                  const tooltipHeight = 230;
                  const left = rect.right + 12 + tooltipWidth <= window.innerWidth
                    ? rect.right + 12
                    : Math.max(12, rect.left - tooltipWidth - 12);
                  setFloatingMarket({
                    holding,
                    left,
                    top: Math.max(12, Math.min(rect.top, window.innerHeight - tooltipHeight - 12)),
                  });
                  void loadMarketSnapshot(holding);
                }}
                onMouseLeave={() => setFloatingMarket(null)}
              >
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
            <div className="holding-row-actions">
              <button
                aria-label={`${holding.ticker} 현재 비중 수정`}
                className="holding-weight-edit"
                disabled={updatingPositionId === holding.id}
                onClick={() => openPositionEditor(holding)}
                type="button"
              >
                수량·비중
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
            {editingPositionId === holding.id && (
              <div className="holding-position-editor">
                <label>
                  <span>보유 수량</span>
                  <input min="0" onChange={(event) => setPositionDraft((current) => ({ ...current, quantity: event.target.value }))} step="0.0001" type="number" value={positionDraft.quantity} />
                </label>
                <label>
                  <span>현재 비중</span>
                  <span className="position-input-suffix"><input max="100" min="0" onChange={(event) => setPositionDraft((current) => ({ ...current, current: event.target.value }))} step="0.1" type="number" value={positionDraft.current} />%</span>
                </label>
                <label>
                  <span>목표 비중</span>
                  <span className="position-input-suffix"><input max="100" min="0" onChange={(event) => setPositionDraft((current) => ({ ...current, target: event.target.value }))} step="0.1" type="number" value={positionDraft.target} />%</span>
                </label>
                <div className="position-editor-actions">
                  <button onClick={() => setEditingPositionId(null)} type="button">취소</button>
                  <button disabled={updatingPositionId === holding.id} onClick={() => { void savePosition(holding); }} type="button">
                    {updatingPositionId === holding.id ? "저장 중…" : "저장"}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {sortedHoldings.length === 0 && <p className="empty-copy holding-empty">등록된 보유 종목이 없습니다.</p>}
      </div>
      {floatingMarket && typeof document !== "undefined" && createPortal(
        <MarketTooltip
          holding={floatingMarket.holding}
          left={floatingMarket.left}
          loading={loadingMarketId === floatingMarket.holding.id}
          snapshot={marketSnapshots[floatingMarket.holding.id]}
          top={floatingMarket.top}
        />,
        document.body,
      )}
    </section>
  );
}

function MarketTooltip({
  holding,
  snapshot,
  loading,
  left,
  top,
}: {
  holding: DashboardHolding;
  snapshot?: MarketSnapshot;
  loading: boolean;
  left: number;
  top: number;
}) {
  const marketValue = snapshot?.current_price != null
    ? snapshot.current_price * holding.quantity
    : null;
  return (
    <span className="market-tooltip market-tooltip--floating" role="tooltip" style={{ left, top }}>
      {loading && <span className="market-tooltip-loading">시세 불러오는 중…</span>}
      {!loading && !snapshot && <span className="market-tooltip-loading">티커에 올리면 시세를 조회합니다.</span>}
      {!loading && snapshot && (
        <>
          <span className="market-tooltip-title"><strong>{snapshot.ticker}</strong><small>{snapshot.as_of ?? "시세 없음"}</small></span>
          <span className="market-price-row"><strong>{snapshot.current_price == null ? "--" : `$${snapshot.current_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}</strong><small className={(snapshot.change_pct_30d ?? 0) >= 0 ? "is-positive" : "is-negative"}>{snapshot.change_pct_30d == null ? "--" : `${snapshot.change_pct_30d > 0 ? "+" : ""}${snapshot.change_pct_30d}% (30D)`}</small></span>
          <span className="market-detail-row"><small>보유 수량</small><strong>{holding.quantity.toLocaleString()}주</strong></span>
          <span className="market-detail-row"><small>평가금액</small><strong>{marketValue == null ? "--" : `$${marketValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}</strong></span>
          <span className="market-detail-row"><small>일중 범위</small><strong>{snapshot.day_low == null || snapshot.day_high == null ? "--" : `$${snapshot.day_low.toFixed(2)} – $${snapshot.day_high.toFixed(2)}`}</strong></span>
          <span className="market-detail-row"><small>거래량</small><strong>{snapshot.volume == null ? "--" : snapshot.volume.toLocaleString()}</strong></span>
        </>
      )}
    </span>
  );
}
