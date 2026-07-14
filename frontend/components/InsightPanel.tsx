import type { Alert, AnalysisResult } from "@/types/schema";

export function InsightPanel({
  concentration,
  alerts,
}: {
  concentration: AnalysisResult | null;
  alerts: Alert[];
}) {
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
          {concentration?.affected_holdings?.map((ticker) => <span key={ticker}>{ticker}</span>)}
        </div>
      </section>

      <section className="panel alert-card">
        <div className="panel-heading compact">
          <h2>Recent Alerts</h2>
          <span className="alert-count">{alerts.length}</span>
        </div>
        {alerts.length === 0 ? (
          <p className="empty-copy">새 알림이 없습니다.</p>
        ) : (
          alerts.map((alert) => (
            <article className="alert-item" key={alert.id}>
              <div><span className={`severity severity--${alert.severity.toLowerCase()}`}>{alert.severity}</span><time>{new Date(alert.created_at).toLocaleDateString("ko-KR")}</time></div>
              <h3>{alert.title}</h3>
              <p>{alert.message}</p>
              {alert.is_sent && (
                <p className="email-delivery-status">
                  Gmail 발송 완료 · {alert.sent_at ? new Date(alert.sent_at).toLocaleString("ko-KR") : "방금"}
                </p>
              )}
            </article>
          ))
        )}
      </section>
    </aside>
  );
}
