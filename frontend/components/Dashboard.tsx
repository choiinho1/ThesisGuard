"use client";

import { useCallback, useEffect, useState } from "react";
import { AddHoldingForm } from "@/components/AddHoldingForm";
import { AllocationPanel } from "@/components/AllocationPanel";
import { HoldingGrid } from "@/components/HoldingGrid";
import { InsightPanel } from "@/components/InsightPanel";
import { PortfolioHeader } from "@/components/PortfolioHeader";
import { ThesisDetail } from "@/components/ThesisDetail";
import {
  analyzeHolding,
  addPortfolioHolding,
  createHoldingThesis,
  getPortfolioDashboard,
  listPortfolios,
  setApiMode,
} from "@/lib/apiClient";
import type {
  ApiMode,
  CreateHoldingInput,
  DashboardHolding,
  HoldingAnalysisResponse,
  PortfolioDashboard,
} from "@/types/schema";

export function Dashboard() {
  const [mode, setMode] = useState<ApiMode>("mock");
  const [dashboard, setDashboard] = useState<PortfolioDashboard | null>(null);
  const [selected, setSelected] = useState<DashboardHolding | null>(null);
  const [analysis, setAnalysis] = useState<HoldingAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async (nextMode: ApiMode) => {
    await Promise.resolve();
    setLoading(true);
    setError(null);
    setDashboard(null);
    setSelected(null);
    setAnalysis(null);
    try {
      const portfolios = await listPortfolios(nextMode);
      if (!portfolios[0]) throw new Error("등록된 포트폴리오가 없습니다.");
      const data = await getPortfolioDashboard(portfolios[0].id, nextMode);
      setDashboard(data);
      setSelected((current) => data.holdings.find((item) => item.id === current?.id) ?? data.holdings[0] ?? null);
      setAnalysis(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // API 모드가 외부 데이터 소스를 결정하므로 모드 변경 때 화면 상태를 다시 동기화한다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDashboard(mode);
  }, [loadDashboard, mode]);

  const changeMode = (nextMode: ApiMode) => {
    if (nextMode === mode) return;
    setDashboard(null);
    setSelected(null);
    setAnalysis(null);
    setError(null);
    setApiMode(nextMode);
    setMode(nextMode);
  };

  const runAnalysis = async () => {
    if (!selected) return;
    setAnalyzing(true);
    setError(null);
    try {
      const result = await analyzeHolding(selected.id, mode);
      setAnalysis(result);
      setSelected((current) => current ? { ...current, thesis: result.thesis, latest_change: result.version } : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === selected.id
          ? { ...item, thesis: result.thesis, latest_change: result.version }
          : item),
      } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분석을 실행하지 못했습니다.");
    } finally {
      setAnalyzing(false);
    }
  };

  const registerThesis = async (rawInput: string) => {
    if (!selected) return;
    setError(null);
    try {
      const thesis = await createHoldingThesis(selected.id, rawInput, mode);
      setSelected((current) => current ? { ...current, thesis } : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === selected.id ? { ...item, thesis } : item),
      } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Thesis를 등록하지 못했습니다.");
    }
  };

  const addHolding = async (input: CreateHoldingInput, rawInput: string) => {
    const portfolioId = dashboard?.portfolio.id;
    if (!portfolioId) return;
    setError(null);
    try {
      const holding = await addPortfolioHolding(portfolioId, input, mode);
      const thesis = rawInput.length >= 10
        ? await createHoldingThesis(holding.id, rawInput, mode)
        : null;
      const created = { ...holding, thesis };
      setDashboard((current) => current ? {
        ...current,
        holdings: [created, ...current.holdings],
      } : current);
      setSelected(created);
      setAnalysis(null);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "종목을 추가하지 못했습니다.";
      setError(message);
      throw new Error(message);
    }
  };

  if (loading && !dashboard) return <main className="loading-screen">ThesisGuard 데이터를 불러오는 중…</main>;
  if (!dashboard) return <main className="loading-screen error-screen">{error ?? "대시보드를 표시할 수 없습니다."}</main>;

  return (
    <main className="app-shell">
      <PortfolioHeader mode={mode} onModeChange={changeMode} portfolio={dashboard.portfolio} />
      {error && <div className="error-banner">{error}</div>}
      <AddHoldingForm
        existingTickers={dashboard.holdings.map((holding) => holding.ticker)}
        onSubmit={addHolding}
      />
      <div className="dashboard-grid">
        <div className="main-column">
          <AllocationPanel holdings={dashboard.holdings} portfolio={dashboard.portfolio} />
          <HoldingGrid holdings={dashboard.holdings} onSelect={(holding) => { setSelected(holding); setAnalysis(null); }} selectedId={selected?.id ?? null} />
        </div>
        <InsightPanel alerts={dashboard.recent_alerts} concentration={dashboard.concentration} />
      </div>
      {selected && <ThesisDetail analysis={analysis} analyzing={analyzing} holding={selected} onAnalyze={runAnalysis} onRegister={registerThesis} />}
      <footer>
        <span>THESISGUARD</span>
        <span>Evidence-led. Explainable. No investment advice.</span>
      </footer>
    </main>
  );
}
