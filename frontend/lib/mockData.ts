import type {
  Alert,
  AnalysisResult,
  CreateHoldingInput,
  DashboardHolding,
  Evidence,
  HoldingAnalysisResponse,
  Portfolio,
  PortfolioDashboard,
  Thesis,
  ThesisVersion,
} from "@/types/schema";

const now = "2026-07-13T02:00:00Z";
const userId = "00000000-0000-4000-8000-000000000001";
const portfolioId = "10000000-0000-4000-8000-000000000001";

export const mockPortfolios: Portfolio[] = [
  {
    id: portfolioId,
    user_id: userId,
    name: "AI Growth Portfolio",
    investment_purpose: "AI 인프라 장기 성장에 분산 투자",
    investment_horizon: "3~5년",
    cash_ratio: 12,
    created_at: "2026-03-02T09:00:00Z",
    updated_at: now,
  },
];

const nvdaThesis: Thesis = {
  id: "30000000-0000-4000-8000-000000000001",
  holding_id: "20000000-0000-4000-8000-000000000001",
  raw_input: "AI 데이터센터 투자 확대가 이어지고 CUDA 생태계가 NVIDIA의 지위를 지킬 것이다.",
  main_thesis: "NVIDIA는 AI 학습·추론 인프라의 표준 지위를 바탕으로 데이터센터 매출 성장을 지속한다.",
  key_assumptions: ["하이퍼스케일러 AI CAPEX가 성장한다", "CUDA 전환 비용이 높게 유지된다"],
  positive_signals: ["클라우드 사업자 가이던스 상향", "차세대 GPU 수요 증가"],
  negative_signals: ["고객사 자체 ASIC 확대", "데이터센터 투자 효율화"],
  key_risks: ["수출 규제 강화", "대형 고객 매출 집중"],
  confidence_score: 82,
  status: "STRENGTHENED",
  created_at: "2026-03-02T09:00:00Z",
  updated_at: now,
};

const avgoThesis: Thesis = {
  id: "30000000-0000-4000-8000-000000000002",
  holding_id: "20000000-0000-4000-8000-000000000002",
  raw_input: "Custom AI ASIC과 네트워크 수요가 Broadcom의 성장을 견인할 것이다.",
  main_thesis: "Broadcom은 Custom AI ASIC과 네트워크 칩 수요 증가로 성장한다.",
  key_assumptions: ["주요 고객의 Custom ASIC 물량이 증가한다"],
  positive_signals: ["AI 반도체 수주 확대"],
  negative_signals: ["고객사 발주 지연"],
  key_risks: ["소수 고객 의존도"],
  confidence_score: 54,
  status: "WEAKENED",
  created_at: "2026-02-10T09:00:00Z",
  updated_at: now,
};

const holdings: DashboardHolding[] = [
  {
    id: nvdaThesis.holding_id,
    portfolio_id: portfolioId,
    ticker: "NVDA",
    company_name: "NVIDIA Corporation",
    quantity: 40,
    avg_buy_price: 118.2,
    target_weight: 35,
    current_weight: 38,
    created_at: "2026-03-02T09:00:00Z",
    updated_at: now,
    thesis: nvdaThesis,
    latest_change: null,
  },
  {
    id: avgoThesis.holding_id,
    portfolio_id: portfolioId,
    ticker: "AVGO",
    company_name: "Broadcom Inc.",
    quantity: 25,
    avg_buy_price: 165,
    target_weight: 25,
    current_weight: 23,
    created_at: "2026-02-10T09:00:00Z",
    updated_at: now,
    thesis: avgoThesis,
    latest_change: null,
  },
  {
    id: "20000000-0000-4000-8000-000000000003",
    portfolio_id: portfolioId,
    ticker: "TSM",
    company_name: "Taiwan Semiconductor Manufacturing",
    quantity: 60,
    avg_buy_price: 142.5,
    target_weight: 20,
    current_weight: 18,
    created_at: "2026-05-12T09:00:00Z",
    updated_at: now,
    thesis: null,
    latest_change: null,
  },
];

const concentration: AnalysisResult = {
  id: "60000000-0000-4000-8000-000000000001",
  portfolio_id: portfolioId,
  thesis_id: null,
  analysis_type: "THESIS_CONCENTRATION",
  bull_summary: null,
  bear_summary: null,
  judge_summary: "AI CAPEX 성장 전제에 대한 의존도가 높습니다.",
  concentration_theme: "AI CAPEX Growth",
  concentration_score: 76,
  affected_holdings: ["NVDA", "AVGO", "TSM"],
  raw_result: {},
  created_at: now,
};

const alerts: Alert[] = [
  {
    id: "70000000-0000-4000-8000-000000000001",
    user_id: userId,
    portfolio_id: portfolioId,
    thesis_id: avgoThesis.id,
    severity: "MAJOR",
    title: "AVGO 투자 논리 약화",
    message: "주요 고객의 발주 일정 지연이 핵심 전제와 충돌합니다.",
    is_sent: true,
    sent_at: now,
    created_at: now,
  },
];

let dashboardState: PortfolioDashboard = {
  portfolio: mockPortfolios[0],
  holdings,
  concentration,
  common_risks: [],
  recent_alerts: alerts,
};

export function getMockDashboard(): PortfolioDashboard {
  return structuredClone(dashboardState);
}

export function addMockHolding(portfolioId: string, input: CreateHoldingInput): DashboardHolding {
  if (dashboardState.holdings.some((item) => item.ticker === input.ticker)) {
    throw new Error(`${input.ticker}는 이미 포트폴리오에 등록되어 있습니다.`);
  }
  const createdAt = new Date().toISOString();
  const holding: DashboardHolding = {
    id: crypto.randomUUID(),
    portfolio_id: portfolioId,
    ticker: input.ticker,
    company_name: input.company_name || input.ticker,
    quantity: input.quantity,
    avg_buy_price: input.avg_buy_price,
    target_weight: input.target_weight,
    current_weight: input.target_weight,
    created_at: createdAt,
    updated_at: createdAt,
    thesis: null,
    latest_change: null,
  };
  dashboardState = {
    ...dashboardState,
    holdings: [holding, ...dashboardState.holdings],
  };
  return structuredClone(holding);
}

export function createMockThesis(holdingId: string, rawInput: string): Thesis {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding) throw new Error("보유 종목을 찾을 수 없습니다.");
  const createdAt = new Date().toISOString();
  const thesis: Thesis = {
    id: crypto.randomUUID(),
    holding_id: holdingId,
    raw_input: rawInput,
    main_thesis: rawInput,
    key_assumptions: ["산업 수요가 투자 기간 동안 성장한다"],
    positive_signals: ["수요 가이던스 상향"],
    negative_signals: ["예상보다 느린 수요 회복"],
    key_risks: ["산업 사이클 변동성"],
    confidence_score: 70,
    status: "UNCHANGED",
    created_at: createdAt,
    updated_at: createdAt,
  };
  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((item) =>
      item.id === holdingId ? { ...item, thesis } : item,
    ),
  };
  return structuredClone(thesis);
}

export function runMockAnalysis(holdingId: string): HoldingAnalysisResponse {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding?.thesis) throw new Error("분석할 Thesis가 없습니다.");

  const updatedThesis: Thesis = {
    ...holding.thesis,
    confidence_score: Math.min(100, holding.thesis.confidence_score + 6),
    status: "STRENGTHENED",
    updated_at: new Date().toISOString(),
  };
  const version: ThesisVersion = {
    id: crypto.randomUUID(),
    thesis_id: updatedThesis.id,
    version_no: 3,
    confidence_score: updatedThesis.confidence_score,
    status: updatedThesis.status,
    change_reason: "핵심 고객사의 신규 수주 공시로 수요 전제가 재확인되었습니다.",
    conflicting_assumptions: [],
    observation_points: ["다음 분기 가이던스 반영 여부"],
    snapshot: updatedThesis,
    created_at: updatedThesis.updated_at,
  };
  const evidence: Evidence[] = [
    {
      id: crypto.randomUUID(),
      thesis_id: updatedThesis.id,
      source_type: "EARNINGS",
      source_url: "https://example.com/earnings",
      vector_doc_id: "earnings-mock-001",
      content_snippet: "주요 고객의 AI 인프라 주문이 전 분기 대비 증가했습니다.",
      classification: "SUPPORT",
      impact: "HIGH",
      reason: "AI CAPEX 성장 전제를 직접 지지합니다.",
      published_at: updatedThesis.updated_at,
      created_at: updatedThesis.updated_at,
    },
  ];
  const analysisResult: AnalysisResult = {
    id: crypto.randomUUID(),
    portfolio_id: dashboardState.portfolio.id,
    thesis_id: updatedThesis.id,
    analysis_type: "BULL_BEAR_JUDGE",
    bull_summary: "신규 수주가 기존 수요 둔화 우려를 반박합니다.",
    bear_summary: "단일 수주의 반복성은 추가 검증이 필요합니다.",
    judge_summary: "지지 근거가 추가되어 신뢰도가 상승했습니다.",
    concentration_theme: null,
    concentration_score: null,
    affected_holdings: null,
    raw_result: { observation_points: version.observation_points },
    created_at: updatedThesis.updated_at,
  };

  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((item) =>
      item.id === holdingId ? { ...item, thesis: updatedThesis, latest_change: version } : item,
    ),
  };
  return structuredClone({
    thesis: updatedThesis,
    version,
    evidence,
    analysis_result: analysisResult,
    alert: null,
  });
}
