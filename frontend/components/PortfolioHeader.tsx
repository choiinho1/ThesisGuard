import type { ApiMode, Portfolio } from "@/types/schema";

interface PortfolioHeaderProps {
  portfolio: Portfolio;
  mode: ApiMode;
  onModeChange: (mode: ApiMode) => void;
}

export function PortfolioHeader({ portfolio, mode, onModeChange }: PortfolioHeaderProps) {
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">THESISGUARD / PORTFOLIO INTELLIGENCE</div>
        <h1>{portfolio.name}</h1>
        <p className="subtitle">
          {portfolio.investment_purpose} · {portfolio.investment_horizon}
        </p>
      </div>
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
    </header>
  );
}
