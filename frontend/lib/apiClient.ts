import { addMockHolding, createMockThesis, getMockDashboard, getMockHoldingHistory, getMockMarketSnapshot, getMockThesisHistory, mockPortfolios, removeMockAlert, removeMockHolding, runMockAnalysis, updateMockHoldingPosition, updateMockHoldingWeight, updateMockThesis } from "@/lib/mockData";
import type {
  ApiMode,
  AnalysisSchedule,
  AnalysisScheduleInput,
  CreateHoldingInput,
  DashboardHolding,
  HoldingAnalysisResponse,
  HoldingHistoryResponse,
  MarketSnapshot,
  Portfolio,
  PortfolioDashboard,
  Thesis,
  ThesisVersion,
  UpdateHoldingPositionInput,
} from "@/types/schema";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const MODE_KEY = "thesisguard_api_mode";

function delay(ms = 180) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window === "undefined" ? null : localStorage.getItem("thesisguard_access_token");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as
      | { detail?: string | Array<{ msg?: string }> }
      | null;
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((item) => item.msg).filter(Boolean).join(" ")
        : null;
    throw new Error(message || `API 요청 실패 (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function optionalRequest<T>(path: string, init?: RequestInit): Promise<T | null> {
  const token = typeof window === "undefined" ? null : localStorage.getItem("thesisguard_access_token");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `API 요청 실패 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getApiMode(): ApiMode {
  if (typeof window === "undefined") return "mock";
  return (localStorage.getItem(MODE_KEY) as ApiMode | null) ??
    (process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock");
}

export function setApiMode(mode: ApiMode) {
  localStorage.setItem(MODE_KEY, mode);
}

export async function listPortfolios(mode = getApiMode()): Promise<Portfolio[]> {
  if (mode === "mock") {
    await delay();
    return structuredClone(mockPortfolios);
  }
  return request<Portfolio[]>("/api/portfolios");
}

export async function getPortfolioDashboard(
  portfolioId: string,
  mode = getApiMode(),
): Promise<PortfolioDashboard> {
  if (mode === "mock") {
    await delay();
    return getMockDashboard();
  }
  return request<PortfolioDashboard>(`/api/portfolios/${portfolioId}/dashboard`);
}

export async function analyzeHolding(
  holdingId: string,
  mode = getApiMode(),
): Promise<HoldingAnalysisResponse> {
  if (mode === "mock") {
    await delay(2200);
    return runMockAnalysis(holdingId);
  }
  return request<HoldingAnalysisResponse>(`/api/holdings/${holdingId}/analyze`, {
    method: "POST",
  });
}

export async function getLatestHoldingAnalysis(
  holdingId: string,
  mode = getApiMode(),
): Promise<HoldingAnalysisResponse | null> {
  if (mode === "mock") return null;
  return optionalRequest<HoldingAnalysisResponse>(`/api/holdings/${holdingId}/analysis`);
}

export async function listAnalysisSchedules(
  mode = getApiMode(),
): Promise<AnalysisSchedule[]> {
  if (mode === "mock") return [];
  return request<AnalysisSchedule[]>("/api/analysis-schedules");
}

export async function saveAnalysisSchedule(
  holdingId: string,
  input: AnalysisScheduleInput,
  mode = getApiMode(),
): Promise<AnalysisSchedule> {
  if (mode === "mock") {
    const now = new Date();
    const [hours, minutes] = input.daily_time.split(":").map(Number);
    const next = new Date(now);
    next.setHours(hours, minutes, 0, 0);
    if (next <= now) next.setDate(next.getDate() + 1);
    return {
      id: `mock-schedule-${holdingId}`,
      holding_id: holdingId,
      ticker: "MOCK",
      enabled: input.enabled,
      daily_time: `${input.daily_time}:00`,
      timezone: input.timezone,
      recipient_email: "mock@thesisguard.local",
      last_run_at: null,
      last_run_status: null,
      next_run_at: next.toISOString(),
    };
  }
  return request<AnalysisSchedule>(`/api/holdings/${holdingId}/analysis-schedule`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function deleteAnalysisSchedule(
  holdingId: string,
  mode = getApiMode(),
): Promise<void> {
  if (mode === "mock") return;
  await request<void>(`/api/holdings/${holdingId}/analysis-schedule`, { method: "DELETE" });
}

export async function createHoldingThesis(
  holdingId: string,
  rawInput: string,
  mode = getApiMode(),
): Promise<Thesis> {
  if (mode === "mock") {
    await delay(350);
    return createMockThesis(holdingId, rawInput);
  }
  return request<Thesis>(`/api/holdings/${holdingId}/thesis`, {
    method: "POST",
    body: JSON.stringify({ raw_input: rawInput }),
  });
}

export async function addPortfolioHolding(
  portfolioId: string,
  input: CreateHoldingInput,
  mode = getApiMode(),
): Promise<DashboardHolding> {
  const normalized = { ...input, ticker: input.ticker.trim().toUpperCase() };
  if (mode === "mock") {
    await delay(280);
    return addMockHolding(portfolioId, normalized);
  }
  const holding = await request<DashboardHolding>(`/api/portfolios/${portfolioId}/holdings`, {
    method: "POST",
    body: JSON.stringify(normalized),
  });
  return { ...holding, thesis: null, latest_change: null };
}

export async function updateHoldingThesis(
  thesisId: string,
  rawInput: string,
  mode = getApiMode(),
): Promise<Thesis> {
  if (mode === "mock") {
    await delay(350);
    return updateMockThesis(thesisId, rawInput);
  }
  return request<Thesis>(`/api/theses/${thesisId}`, {
    method: "PUT",
    body: JSON.stringify({ raw_input: rawInput }),
  });
}

export async function deletePortfolioHolding(
  holdingId: string,
  mode = getApiMode(),
): Promise<void> {
  if (mode === "mock") {
    await delay(180);
    removeMockHolding(holdingId);
    return;
  }
  await request<void>(`/api/holdings/${holdingId}`, { method: "DELETE" });
}

export async function deleteAlert(alertId: string, mode = getApiMode()): Promise<void> {
  if (mode === "mock") {
    await delay(120);
    removeMockAlert(alertId);
    return;
  }
  await request<void>(`/api/alerts/${alertId}`, { method: "DELETE" });
}

export async function getThesisHistory(
  thesisId: string,
  mode = getApiMode(),
): Promise<ThesisVersion[]> {
  if (mode === "mock") {
    await delay(120);
    return getMockThesisHistory(thesisId);
  }
  return request<ThesisVersion[]>(`/api/theses/${thesisId}/history`);
}

export async function updateHoldingCurrentWeight(
  holdingId: string,
  currentWeight: number,
  mode = getApiMode(),
): Promise<DashboardHolding> {
  if (mode === "mock") {
    await delay(180);
    return updateMockHoldingWeight(holdingId, currentWeight);
  }
  const holding = await request<DashboardHolding>(`/api/holdings/${holdingId}`, {
    method: "PUT",
    body: JSON.stringify({ current_weight: currentWeight }),
  });
  return { ...holding, thesis: null, latest_change: null };
}

export async function updateHoldingPosition(
  holdingId: string,
  input: UpdateHoldingPositionInput,
  mode = getApiMode(),
): Promise<DashboardHolding> {
  if (mode === "mock") {
    await delay(180);
    return updateMockHoldingPosition(holdingId, input);
  }
  const holding = await request<DashboardHolding>(`/api/holdings/${holdingId}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
  return { ...holding, thesis: null, latest_change: null };
}

export async function getHoldingMarketSnapshot(
  holdingId: string,
  ticker: string,
  mode = getApiMode(),
): Promise<MarketSnapshot> {
  if (mode === "mock") {
    await delay(140);
    return getMockMarketSnapshot(ticker);
  }
  return request<MarketSnapshot>(`/api/holdings/${holdingId}/market-snapshot`);
}

export async function getHoldingHistory(
  holdingId: string,
  options: { limit?: number; offset?: number } = {},
  mode = getApiMode(),
): Promise<HoldingHistoryResponse> {
  const limit = options.limit ?? 30;
  const offset = options.offset ?? 0;
  if (mode === "mock") {
    await delay(160);
    return getMockHoldingHistory(holdingId);
  }
  return request<HoldingHistoryResponse>(
    `/api/holdings/${holdingId}/history?limit=${limit}&offset=${offset}`,
  );
}

export { API_BASE_URL };
