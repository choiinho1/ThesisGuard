import { StatusBadge } from "@/components/StatusBadge";
import type { DashboardHolding } from "@/types/schema";

export function HoldingGrid({
  holdings,
  selectedId,
  onSelect,
}: {
  holdings: DashboardHolding[];
  selectedId: string | null;
  onSelect: (holding: DashboardHolding) => void;
}) {
  return (
    <section className="panel holdings-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">02</span>
          <h2>Thesis Monitor</h2>
        </div>
        <span className="panel-meta">{holdings.length} HOLDINGS</span>
      </div>
      <div className="holding-table">
        {holdings.map((holding) => (
          <button
            className={`holding-row ${selectedId === holding.id ? "is-selected" : ""}`}
            key={holding.id}
            onClick={() => onSelect(holding)}
            type="button"
          >
            <span className="ticker-cell">
              <strong>{holding.ticker}</strong>
              <small>{holding.company_name}</small>
            </span>
            <span className="weight-cell">
              <small>현재 / 목표</small>
              <strong>
                {holding.current_weight}% / {holding.target_weight}%
              </strong>
            </span>
            <span className="confidence-cell">
              <small>Confidence</small>
              <strong>{holding.thesis?.confidence_score ?? "--"}</strong>
            </span>
            <span>
              {holding.thesis ? <StatusBadge status={holding.thesis.status} /> : <span className="status">미등록</span>}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
