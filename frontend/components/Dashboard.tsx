"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AddHoldingForm } from "@/components/AddHoldingForm";
import { AutoAnalysisSchedule } from "@/components/AutoAnalysisSchedule";
import { AllocationPanel } from "@/components/AllocationPanel";
import { HoldingGrid } from "@/components/HoldingGrid";
import { InsightPanel } from "@/components/InsightPanel";
import { PortfolioHeader } from "@/components/PortfolioHeader";
import { PortfolioQueryPanel } from "@/components/PortfolioQueryPanel";
import { SavedEvidenceHistory } from "@/components/SavedEvidenceHistory";
import { ThesisDetail } from "@/components/ThesisDetail";
import {
  analyzeHolding,
  addPortfolioHolding,
  createHoldingThesis,
  deletePortfolioHolding,
  deleteAlert,
  getPortfolioDashboard,
  getLatestHoldingAnalysis,
  getHoldingMarketSnapshot,
  getApiMode,
  listPortfolios,
  setApiMode,
  updateHoldingPosition,
  updateHoldingThesis,
  updateThesisLogicOperator,
} from "@/lib/apiClient";
import { getMockDashboard } from "@/lib/mockData";
import type {
  ApiMode,
  CreateHoldingInput,
  DashboardHolding,
  HoldingAnalysisResponse,
  LogicOperator,
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
  const [activeSection, setActiveSection] = useState<"main" | "qa" | "history">("main");
  const selectedIdRef = useRef<string | null>(null);
  const loadedModeRef = useRef<ApiMode>("mock");

  useEffect(() => {
    selectedIdRef.current = selected?.id ?? null;
  }, [selected]);

  useEffect(() => {
    // This one-time hydration sync applies the user's persisted API mode.
    /* eslint-disable react-hooks/set-state-in-effect */
    const preferredMode = getApiMode();
    if (preferredMode !== mode) {
      // Mock-seeded holding IDs (e.g. "20000000-...") don't exist on the
      // real backend. Clear them here, in the same effect that flips the
      // mode, so the live-analysis-fetch effect below never runs against a
      // stale mock holding before loadDashboard() gets a chance to replace it.
      if (preferredMode !== "mock") {
        setDashboard(null);
        setSelected(null);
      }
      setMode(preferredMode);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (mode !== "live" || !selected?.thesis) return;
    let cancelled = false;
    const holdingId = selected.id;
    void getLatestHoldingAnalysis(holdingId, mode)
      .then((result) => {
        if (!cancelled && selectedIdRef.current === holdingId) setAnalysis(result);
      })
      .catch(() => {
        // A holding without a completed analysis legitimately has no result yet.
      });
    return () => { cancelled = true; };
  }, [mode, selected?.id, selected?.thesis]);

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
      const message = caught instanceof Error ? caught.message : "데이터를 불러오지 못했습니다.";
      // Live mode needs a valid backend session. With a stale/expired token —
      // or in the demo-bypass build, which never shows a login form to obtain
      // one — nulling the dashboard would strand the user on an error screen
      // that renders no mode switch, so there's no way back to mock. Fall back
      // to mock automatically and explain why, keeping the app usable.
      if (nextMode === "live") {
        setApiMode("mock");
        loadedModeRef.current = "mock";
        setMode("mock");
        const fallback = getMockDashboard();
        setDashboard(fallback);
        setSelected(fallback.holdings[0] ?? null);
        setError(
          "실시간(LIVE) 데이터를 불러오지 못해 데모(MOCK) 모드로 전환했습니다. " +
            `실시간 모드는 로그인이 필요합니다. (원인: ${message})`,
        );
        return;
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Compare against the last mode we actually loaded (not a "have we run
    // yet" flag) so this stays idempotent under React Strict Mode's
    // mount -> cleanup -> mount double-invocation in dev. A mutable
    // "already ran once" ref behaves differently on the 2nd invocation than
    // the 1st, which let a stray loadDashboard("mock") slip through and
    // re-seed mock holding IDs right as the mode flipped to "live".
    if (mode === loadedModeRef.current) return;
    loadedModeRef.current = mode;
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
    if (mode === "mock") {
      window.localStorage.removeItem(`thesisguard_saved_evidence_${holdingId}`);
    }
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

      // The create request has already succeeded, so reflect it immediately.
      // A live dashboard refresh enriches weights and aggregate data, but must
      // not make a successful addition look like a failure if that refresh is
      // temporarily unavailable.
      setDashboard((current) => current ? {
        ...current,
        holdings: [created, ...current.holdings.filter((item) => item.id !== created.id)],
      } : current);
      setSelected(created);
      setAnalysis(null);

      void getPortfolioDashboard(portfolioId, mode)
        .then((refreshed) => {
          const refreshedHolding = refreshed.holdings.find((item) => item.id === holding.id)
            ?? created;
          setDashboard(refreshed);
          setSelected((current) => current?.id === holding.id ? refreshedHolding : current);
        })
        .catch(() => {
          // Keep the successfully created holding visible. A later dashboard
          // load will reconcile aggregate data.
        });
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
    if (mode === "mock") {
      window.localStorage.removeItem(`thesisguard_saved_evidence_${holdingId}`);
    }
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

  const updateLogicOperator = async (nodeId: string, operator: LogicOperator) => {
    if (!selected?.thesis) return;
    const holdingId = selected.id;
    const thesisId = selected.thesis.id;
    setError(null);
    if (mode === "mock") {
      window.localStorage.removeItem(`thesisguard_saved_evidence_${holdingId}`);
    }
    try {
      const thesis = await updateThesisLogicOperator(thesisId, nodeId, operator, mode);
      setAnalysis(null);
      setSelected((current) => current?.id === holdingId ? { ...current, thesis } : current);
      setDashboard((current) => current ? {
        ...current,
        holdings: current.holdings.map((item) =>
          item.id === holdingId ? { ...item, thesis } : item,
        ),
      } : current);
    } catch (caught) {
      const message = caught instanceof Error
        ? caught.message
        : "논리 연결 방식을 변경하지 못했습니다.";
      setError(message);
      throw new Error(message);
    }
  };

  const deleteHolding = async (holding: DashboardHolding) => {
    setError(null);
    try {
      await deletePortfolioHolding(holding.id, mode);
      const refreshed = await getPortfolioDashboard(holding.portfolio_id, mode);
      setDashboard(refreshed);
      setSelected((selectedHolding) => refreshed.holdings.find(
        (item) => item.id === selectedHolding?.id,
      ) ?? refreshed.holdings[0] ?? null);
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
      await updateHoldingPosition(holding.id, input, mode);
      // Dashboard reload recalculates every holding's current_weight from
      // quantity × latest quote, so users never edit allocation percentages.
      const refreshed = await getPortfolioDashboard(holding.portfolio_id, mode);
      setDashboard(refreshed);
      setSelected((current) => refreshed.holdings.find((item) => item.id === current?.id)
        ?? refreshed.holdings[0]
        ?? null);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "보유 수량을 수정하지 못했습니다.";
      setError(message);
      throw new Error(message);
    }
  };

  if (loading && !dashboard) return <main className="loading-screen">ThesisGuard 데이터를 불러오는 중…</main>;
  if (!dashboard) {
    return (
      <main className="loading-screen error-screen">
        <p>{error ?? "대시보드를 표시할 수 없습니다."}</p>
        <button
          className="primary-button"
          onClick={() => {
            const fallback = getMockDashboard();
            setApiMode("mock");
            loadedModeRef.current = "mock";
            setDashboard(fallback);
            setSelected(fallback.holdings[0] ?? null);
            setError(null);
            setMode("mock");
          }}
          type="button"
        >
          데모(MOCK) 모드로 전환
        </button>
      </main>
    );
  }

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
          aria-current={activeSection === "qa" ? "page" : undefined}
          className={activeSection === "qa" ? "is-active" : ""}
          onClick={() => setActiveSection("qa")}
          type="button"
        >
          Q&amp;A
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
      {activeSection === "main" && selected && (
        <AutoAnalysisSchedule holding={selected} mode={mode} />
      )}
      {activeSection === "main" && selected && <ThesisDetail key={selected.id} analysis={analysis} analyzing={analyzing} holding={selected} mode={mode} onAnalyze={runAnalysis} onOperatorChange={updateLogicOperator} onRegister={registerThesis} onUpdate={updateThesisAndAnalyze} />}
      {activeSection === "qa" && (
        <PortfolioQueryPanel
          key={dashboard.portfolio.id}
          holdingCount={dashboard.holdings.length}
          mode={mode}
          portfolioId={dashboard.portfolio.id}
          thesisCount={dashboard.holdings.filter((holding) => holding.thesis).length}
        />
      )}
      {activeSection === "history" && <SavedEvidenceHistory holdings={dashboard.holdings} mode={mode} portfolioId={dashboard.portfolio.id} selectedHoldingId={selected?.id ?? null} />}
      <footer>
        <span>THESISGUARD</span>
        <span>Evidence-led. Explainable. No investment advice.</span>
      </footer>
    </main>
  );
}
