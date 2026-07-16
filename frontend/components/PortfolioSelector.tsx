"use client";

import { FormEvent, useEffect, useState } from "react";
import { createPortfolio, deletePortfolio, listPortfolios } from "@/lib/apiClient";
import type { ApiMode, Portfolio } from "@/types/schema";

interface PortfolioSelectorProps {
  mode: ApiMode;
  onModeChange: (mode: ApiMode) => void;
  onSelect: (portfolio: Portfolio) => void;
}

export function PortfolioSelector({ mode, onModeChange, onSelect }: PortfolioSelectorProps) {
  const [portfolios, setPortfolios] = useState<Portfolio[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [horizon, setHorizon] = useState("");
  const [cashRatio, setCashRatio] = useState("0");

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setLoading(true);
      setError(null);
      return listPortfolios(mode)
        .then((result) => {
          if (!cancelled) setPortfolios(result);
        })
        .catch((caught) => {
          if (!cancelled) {
            setError(caught instanceof Error ? caught.message : "포트폴리오를 불러오지 못했습니다.");
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    });
    return () => { cancelled = true; };
  }, [mode]);

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await createPortfolio(
        {
          name: name.trim(),
          investment_purpose: purpose.trim() || undefined,
          investment_horizon: horizon.trim() || undefined,
          cash_ratio: cashRatio.trim() ? Number(cashRatio) : undefined,
        },
        mode,
      );
      setPortfolios((current) => [...(current ?? []), created]);
      onSelect(created);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "포트폴리오를 생성하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (portfolio: Portfolio) => {
    if (!window.confirm(`${portfolio.name} 포트폴리오를 삭제할까요? 포함된 보유 종목, Thesis, 분석·알림 기록이 모두 함께 삭제됩니다.`)) return;
    setDeletingId(portfolio.id);
    setError(null);
    try {
      await deletePortfolio(portfolio.id, mode);
      setPortfolios((current) => (current ?? []).filter((item) => item.id !== portfolio.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "포트폴리오를 삭제하지 못했습니다.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main className="portfolio-select-shell">
      <div className="portfolio-select-card">
        <div className="portfolio-select-heading">
          <div>
            <div className="eyebrow">THESISGUARD / PORTFOLIO INTELLIGENCE</div>
            <h1>포트폴리오를 선택하세요</h1>
            <p className="subtitle">확인하거나 관리할 포트폴리오를 골라주세요.</p>
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
        </div>

        {error && <div className="error-banner">{error}</div>}

        {loading && <p className="portfolio-select-loading">불러오는 중...</p>}

        {!loading && portfolios && portfolios.length === 0 && !creating && (
          <p className="portfolio-select-loading">등록된 포트폴리오가 없습니다. 새로 만들어 보세요.</p>
        )}

        {!loading && portfolios && portfolios.length > 0 && (
          <div className="portfolio-select-grid">
            {portfolios.map((portfolio) => (
              <div className="portfolio-select-item" key={portfolio.id}>
                <button
                  className="portfolio-select-item-main"
                  onClick={() => onSelect(portfolio)}
                  type="button"
                >
                  <strong>{portfolio.name}</strong>
                  <span>{[portfolio.investment_purpose, portfolio.investment_horizon].filter(Boolean).join(" · ") || "설명 없음"}</span>
                  <small>현금 비중 {portfolio.cash_ratio}%</small>
                </button>
                <button
                  className="portfolio-delete"
                  disabled={deletingId === portfolio.id}
                  onClick={() => { void handleDelete(portfolio); }}
                  type="button"
                >
                  {deletingId === portfolio.id ? "삭제 중..." : "삭제"}
                </button>
              </div>
            ))}
          </div>
        )}

        {creating ? (
          <form className="portfolio-create-form" onSubmit={handleCreate}>
            <label>
              <span>포트폴리오 이름</span>
              <input onChange={(event) => setName(event.target.value)} required type="text" value={name} placeholder="예: AI Growth Portfolio" />
            </label>
            <div className="portfolio-create-fields">
              <label>
                <span>투자 목적 <small>선택</small></span>
                <input onChange={(event) => setPurpose(event.target.value)} type="text" value={purpose} placeholder="예: 장기 자산 성장" />
              </label>
              <label>
                <span>투자 기간 <small>선택</small></span>
                <input onChange={(event) => setHorizon(event.target.value)} type="text" value={horizon} placeholder="예: 3~5년" />
              </label>
              <label>
                <span>현금 비중(%) <small>선택</small></span>
                <input min={0} max={100} onChange={(event) => setCashRatio(event.target.value)} type="number" value={cashRatio} />
              </label>
            </div>
            <div className="add-form-actions">
              <button className="secondary-button" disabled={submitting} onClick={() => setCreating(false)} type="button">취소</button>
              <button className="auth-submit" disabled={submitting || !name.trim()} type="submit">
                <span>{submitting ? "생성하는 중..." : "포트폴리오 만들기"}</span>
              </button>
            </div>
          </form>
        ) : (
          <button className="portfolio-select-new" disabled={loading} onClick={() => setCreating(true)} type="button">
            + 새 포트폴리오 만들기
          </button>
        )}
      </div>
    </main>
  );
}
