"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AddHoldingForm } from "@/components/AddHoldingForm";
import { AllocationPanel } from "@/components/AllocationPanel";
import { HoldingGrid } from "@/components/HoldingGrid";
import { InsightPanel } from "@/components/InsightPanel";
import { PortfolioHeader } from "@/components/PortfolioHeader";
import { SavedEvidenceHistory } from "@/components/SavedEvidenceHistory";
import { ThesisDetail } from "@/components/ThesisDetail";
import {
  analyzeHolding,
  addPortfolioHolding,
  createHoldingThesis,
  deletePortfolioHolding,
  deleteAlert,
  getPortfolioDashboard,
  getHoldingMarketSnapshot,
  listPortfolios,
  setApiMode,
  updateHoldingPosition,
  updateHoldingThesis,
} from "@/lib/apiClient";
import { getMockDashboard } from "@/lib/mockData";
import type {
  ApiMode,
  CreateHoldingInput,
  DashboardHolding,
  HoldingAnalysisResponse,
  PortfolioDashboard,
  UpdateHoldingPositionInput,
} from "@/types/schema";

export function Dashboard() {
  const initialMockDashboard = getMockDashboard();
  const [mode, setMode] = useState<ApiMode>("mock");
  const [dashboard, setDashboard] = useState<PortfolioDashboard | null>(initialMockDashboard);
  const [selected, setSelected] = useState<DashboardHolding | null>(
    initialMockDashboard.holdings[0] ?? null,
  );
  const [analysis, setAnalysis] = useState<HoldingAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<"main" | "history">("main");
  const selectedIdRef = useRef<string | null>(null);
  const skippedInitialMockLoadRef = useRef(false);

  useEffect(() => {
    selectedIdRef.current = selected?.id ?? null;
  }, [selected]);

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
    if (mode === "mock" && !skippedInitialMockLoadRef.current) {
      skippedInitialMockLoadRef.current = true;
      return;
    }
    // API 모드가 외부 데이터 소스를 결정하므로 모드 변경 때 화면 상태를 다시 동기화한다.
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

  const refreshPortfolioAnalysis = async (portfolioId: string) => {
    try {
      const refreshed = await getPortfolioDashboard(portfolioId, mode);
      setDashboard(refreshed);
      setSelected((current) => refreshed.holdings.find((item) => item.id === current?.id)
        ?? refreshed.holdings[0]
        ?? null);
    } catch {
      setError("분석은 완료됐지만 포트폴리오 집중도 화면을 새로고침하지 못했습니다.");
    }
  };

  const runAnalysis = async () => {
    if (!selected) return;
    const holdingId = selected.id;
    setAnalyzing(true);
    setError(null);
    try {
      const result = await analyzeHolding(holdingId, mode);
      setSelected((current) => current?.id === holdingId
        ? { ...current, thesis: result.thesis, latest_change: result.version }
        : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === holdingId
          ? { ...item, thesis: result.thesis, latest_change: result.version }
          : item),
        recent_alerts: result.alert
          ? [result.alert, ...current.recent_alerts.filter((item) => item.id !== result.alert?.id)]
          : current.recent_alerts,
      } : current);
      if (selectedIdRef.current === holdingId) setAnalysis(result);
      await refreshPortfolioAnalysis(selected.portfolio_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분석을 실행하지 못했습니다.");
    } finally {
      setAnalyzing(false);
    }
  };

  const registerThesis = async (rawInput: string) => {
    if (!selected) return;
    const holdingId = selected.id;
    setError(null);
    try {
      const thesis = await createHoldingThesis(holdingId, rawInput, mode);
      setSelected((current) => current?.id === holdingId ? { ...current, thesis } : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === holdingId ? { ...item, thesis } : item),
      } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Thesis를 등록하지 못했습니다.");
    }
  };

  const addHolding = async (input: CreateHoldingInput) => {
    const portfolioId = dashboard?.portfolio.id;
    if (!portfolioId) return;
    setError(null);
    try {
      const holding = await addPortfolioHolding(portfolioId, input, mode);
      const created = { ...holding, thesis: null };
      if (mode === "live") {
        const refreshed = await getPortfolioDashboard(portfolioId, mode);
        const refreshedHolding = refreshed.holdings.find((item) => item.id === holding.id)
          ?? created;
        setDashboard(refreshed);
        setSelected(refreshedHolding);
        setAnalysis(null);
        return;
      }
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

  const updateThesisAndAnalyze = async (rawInput: string) => {
    if (!selected?.thesis) return;
    const holdingId = selected.id;
    const thesisId = selected.thesis.id;
    setAnalyzing(true);
    setError(null);
    try {
      const updatedThesis = await updateHoldingThesis(thesisId, rawInput, mode);
      setSelected((current) => current?.id === holdingId
        ? { ...current, thesis: updatedThesis }
        : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === holdingId
          ? { ...item, thesis: updatedThesis }
          : item),
      } : current);

      const result = await analyzeHolding(holdingId, mode);
      if (selectedIdRef.current === holdingId) setAnalysis(result);
      setSelected((current) => current?.id === holdingId
        ? { ...current, thesis: result.thesis, latest_change: result.version }
        : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === holdingId
          ? { ...item, thesis: result.thesis, latest_change: result.version }
          : item),
      } : current);
      await refreshPortfolioAnalysis(selected.portfolio_id);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "투자 논리를 수정하지 못했습니다.";
      setError(message);
      throw new Error(message);
    } finally {
      setAnalyzing(false);
    }
  };

  const deleteHolding = async (holding: DashboardHolding) => {
    setError(null);
    try {
      await deletePortfolioHolding(holding.id, mode);
      if (mode === "live") {
        const refreshed = await getPortfolioDashboard(holding.portfolio_id, mode);
        setDashboard(refreshed);
        setSelected(refreshed.holdings[0] ?? null);
        setAnalysis(null);
        return;
      }
      const remaining = dashboard?.holdings.filter((item) => item.id !== holding.id) ?? [];
      setDashboard((current) => current ? { ...current, holdings: remaining } : current);
      setSelected((selectedHolding) => selectedHolding?.id === holding.id
        ? remaining[0] ?? null
        : selectedHolding);
      setAnalysis(null);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "보유 종목을 삭제하지 못했습니다.";
      setError(message);
      throw new Error(message);
    }
  };

  const removeAlert = async (alert: import("@/types/schema").Alert) => {
    setError(null);
    try {
      await deleteAlert(alert.id, mode);
      setDashboard((current) => current ? {
        ...current,
        recent_alerts: current.recent_alerts.filter((item) => item.id !== alert.id),
      } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "알림을 삭제하지 못했습니다.");
    }
  };

  const updatePosition = async (
    holding: DashboardHolding,
    input: UpdateHoldingPositionInput,
  ) => {
    setError(null);
    try {
      const updated = await updateHoldingPosition(holding.id, input, mode);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) => item.id === holding.id
          ? {
              ...item,
              quantity: updated.quantity,
              current_weight: updated.current_weight,
              target_weight: updated.target_weight,
              updated_at: updated.updated_at,
            }
          : item),
      } : current);
      setSelected((current) => current?.id === holding.id
        ? {
            ...current,
            quantity: updated.quantity,
            current_weight: updated.current_weight,
            target_weight: updated.target_weight,
            updated_at: updated.updated_at,
          }
        : current);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "수량과 비중을 수정하지 못했습니다.";
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
          <HoldingGrid holdings={dashboard.holdings} onDelete={deleteHolding} onLoadMarketSnapshot={(holding) => getHoldingMarketSnapshot(holding.id, holding.ticker, mode)} onSelect={(holding) => { setSelected(holding); setAnalysis(null); }} onUpdatePosition={updatePosition} selectedId={selected?.id ?? null} />
        </div>
        <InsightPanel
          alerts={dashboard.recent_alerts}
          commonRisks={dashboard.common_risks}
          concentration={dashboard.concentration}
          holdings={dashboard.holdings}
          onDeleteAlert={removeAlert}
        />
      </div>
      <nav className="workspace-tabs" aria-label="Thesis workspace">
        <button
          aria-current={activeSection === "main" ? "page" : undefined}
          className={activeSection === "main" ? "is-active" : ""}
          onClick={() => setActiveSection("main")}
          type="button"
        >
          Main
        </button>
        <button
          aria-current={activeSection === "history" ? "page" : undefined}
          className={activeSection === "history" ? "is-active" : ""}
          onClick={() => setActiveSection("history")}
          type="button"
        >
          History
        </button>
      </nav>
      {activeSection === "main" && selected && <ThesisDetail key={selected.id} analysis={analysis} analyzing={analyzing} holding={selected} onAnalyze={runAnalysis} onRegister={registerThesis} onUpdate={updateThesisAndAnalyze} />}
      {activeSection === "history" && <SavedEvidenceHistory holdings={dashboard.holdings} mode={mode} />}
      <footer>
        <span>THESISGUARD</span>
        <span>Evidence-led. Explainable. No investment advice.</span>
      </footer>
    </main>
  );
}
