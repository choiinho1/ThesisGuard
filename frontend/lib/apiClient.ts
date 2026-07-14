import { addMockHolding, createMockThesis, getMockDashboard, mockPortfolios, removeMockHolding, runMockAnalysis, updateMockThesis } from "@/lib/mockData";
import type {
  ApiMode,
  CreateHoldingInput,
  DashboardHolding,
  HoldingAnalysisResponse,
  Portfolio,
  PortfolioDashboard,
  Thesis,
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

export { API_BASE_URL };
