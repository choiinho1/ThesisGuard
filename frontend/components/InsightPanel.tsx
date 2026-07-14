import type { Alert, AnalysisResult, DashboardHolding } from "@/types/schema";

function resolveAffectedTickers(
  affectedHoldings: string[] | null | undefined,
  holdings: DashboardHolding[],
) {
  const tickerByHoldingId = new Map(holdings.map((holding) => [holding.id, holding.ticker]));
  const canonicalTicker = new Map(
    holdings.map((holding) => [holding.ticker.toUpperCase(), holding.ticker]),
  );

  return Array.from(new Set(
    (affectedHoldings ?? []).flatMap((value) => {
      const ticker = tickerByHoldingId.get(value)
        ?? canonicalTicker.get(value.toUpperCase());
      return ticker ? [ticker] : [];
    }),
  ));
}

export function InsightPanel({
  concentration,
  commonRisks,
  alerts,
  onDeleteAlert,
  holdings,
}: {
  concentration: AnalysisResult | null;
  commonRisks: AnalysisResult[];
  alerts: Alert[];
  onDeleteAlert: (alert: Alert) => Promise<void>;
  holdings: DashboardHolding[];
}) {
  const affectedTickers = resolveAffectedTickers(concentration?.affected_holdings, holdings);
  const visibleCommonRisks = commonRisks.flatMap((risk) => {
    const tickers = resolveAffectedTickers(risk.affected_holdings, holdings);
    return risk.concentration_theme && tickers.length >= 2
      ? [{ id: risk.id, label: risk.concentration_theme, tickers }]
      : [];
  });

  return (
    <aside className="insight-column">
      <section className="panel concentration-card">
        <span className="section-index">03</span>
        <p className="kicker">THESIS CONCENTRATION</p>
        <div className="score-ring" style={{ "--score": concentration?.concentration_score ?? 0 } as React.CSSProperties}>
          <strong>{concentration?.concentration_score ?? "--"}</strong>
          <span>%</span>
        </div>
        <h2>{concentration?.concentration_theme ?? "집중 테마 없음"}</h2>
        <p>{concentration?.judge_summary ?? "공통 전제가 감지되지 않았습니다."}</p>
        <div className="ticker-chips">
          {affectedTickers.map((ticker) => <span key={ticker}>{ticker}</span>)}
        </div>
        {visibleCommonRisks.length > 0 && (
          <div className="common-risk-list">
            <h3>공통 위험</h3>
            {visibleCommonRisks.map((risk) => (
              <article key={risk.id}>
                <strong>{risk.label}</strong>
                <span>{risk.tickers.join(" · ")}</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel alert-card">
        <div className="panel-heading compact">
          <h2>Recent Alerts</h2>
          <span className="alert-count">{alerts.length}</span>
        </div>
        {alerts.length === 0 ? (
          <p className="empty-copy">새 알림이 없습니다.</p>
        ) : (
          <div className="alert-list" role="region" aria-label="최근 알림 목록" tabIndex={0}>
          {alerts.map((alert) => (
            <article className="alert-item" key={alert.id}>
              <div className="alert-item-heading"><span className={`severity severity--${alert.severity.toLowerCase()}`}>{alert.severity}</span><time>{new Date(alert.created_at).toLocaleDateString("ko-KR")}</time><button className="alert-delete" onClick={() => void onDeleteAlert(alert)} type="button" aria-label={`${alert.title} 삭제`}>삭제</button></div>
              <h3>{alert.title}</h3>
              <p>{alert.message}</p>
              {alert.is_sent && (
                <p className="email-delivery-status">
                  Gmail 발송 완료 · {alert.sent_at ? new Date(alert.sent_at).toLocaleString("ko-KR") : "방금"}
                </p>
              )}
            </article>
          ))}
          </div>
        )}
      </section>
    </aside>
  );
}
