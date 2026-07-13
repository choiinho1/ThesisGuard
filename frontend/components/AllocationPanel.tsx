import type { DashboardHolding, Portfolio } from "@/types/schema";

const colors = ["#5be6b0", "#8aa8ff", "#f4bc67", "#8090a5"];

export function AllocationPanel({
  portfolio,
  holdings,
}: {
  portfolio: Portfolio;
  holdings: DashboardHolding[];
}) {
  const rows = [
    ...holdings.map((holding, index) => ({
      label: holding.ticker,
      value: holding.current_weight,
      color: colors[index % colors.length],
    })),
    { label: "CASH", value: portfolio.cash_ratio, color: colors[3] },
  ];

  return (
    <section className="panel allocation-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">01</span>
          <h2>Allocation</h2>
        </div>
        <span className="panel-meta">CURRENT WEIGHT</span>
      </div>
      <div className="allocation-stack" aria-label="포트폴리오 현재 비중">
        {rows.map((row) => (
          <div key={row.label} style={{ width: `${row.value}%`, background: row.color }} />
        ))}
      </div>
      <div className="allocation-list">
        {rows.map((row) => (
          <div className="allocation-row" key={row.label}>
            <span className="dot" style={{ background: row.color }} />
            <strong>{row.label}</strong>
            <span>{row.value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </section>
  );
}
