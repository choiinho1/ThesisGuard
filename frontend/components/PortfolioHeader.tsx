import type { ApiMode, Portfolio } from "@/types/schema";

interface PortfolioHeaderProps {
  portfolio: Portfolio;
  mode: ApiMode;
  onModeChange: (mode: ApiMode) => void;
  onSwitchPortfolio: () => void;
}

export function PortfolioHeader({ portfolio, mode, onModeChange, onSwitchPortfolio }: PortfolioHeaderProps) {
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">THESISGUARD / PORTFOLIO INTELLIGENCE</div>
        <h1>{portfolio.name}</h1>
        <p className="responsibility-notice">
          이 화면은 투자 권고가 아니며, <strong>최종 투자 판단과 그 결과에 대한 책임은 투자자 본인에게 있습니다.</strong>
        </p>
        <p className="subtitle">
          {portfolio.investment_purpose} · {portfolio.investment_horizon}
        </p>
      </div>
      <div className="topbar-actions">
        <button className="portfolio-switch-button" onClick={onSwitchPortfolio} type="button">
          포트폴리오 변경
        </button>
        <div className="mode-switch" aria-label="API 모드">
          {(["mock", "live"] as const).map((item) => (
            <button
              className={mode === item ? "is-active" : ""}
              key={item}
              onClick={() => onModeChange(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
