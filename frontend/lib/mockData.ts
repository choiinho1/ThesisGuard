import type {
  AdminHealth,
  AdminScheduleOverview,
  Alert,
  AnalysisResult,
  AppSetting,
  CreateHoldingInput,
  DashboardHolding,
  EvalRun,
  EvalScenario,
  EvalScenarioInput,
  Evidence,
  HoldingAnalysisResponse,
  HoldingHistoryResponse,
  LangfuseTrace,
  LogicOperator,
  MarketSnapshot,
  Portfolio,
  PortfolioDashboard,
  PortfolioQueryEvidence,
  PortfolioQueryResponse,
  PortfolioQueryScope,
  QaLogEntry,
  Thesis,
  ThesisVersion,
  UpdateHoldingPositionInput,
} from "@/types/schema";

const now = "2026-07-13T02:00:00Z";
const userId = "00000000-0000-4000-8000-000000000001";
const portfolioId = "10000000-0000-4000-8000-000000000001";

function mockLogicGraph(
  mainThesis: string,
  assumptions: string[],
): NonNullable<Thesis["logic_graph"]> {
  const leaves = assumptions.map((assumption, index) => ({
    node_id: `assumption_${index + 1}`,
    kind: "ASSUMPTION" as const,
    label: assumption,
    operator: null,
    child_ids: [],
    assumption,
  }));
  return {
    graph_version: "1.0.0",
    root_id: "root_claim",
    nodes: [{
      node_id: "root_claim",
      kind: "CLAIM",
      label: mainThesis,
      operator: "CONTRIBUTING",
      child_ids: leaves.map((node) => node.node_id),
      assumption: null,
    }, ...leaves],
  };
}

function mockScoreBreakdown(
  graph: NonNullable<Thesis["logic_graph"]>,
  healthScore: number,
): NonNullable<Thesis["score_breakdown"]> {
  const rootState = healthScore / 50;
  const rootVerdict = rootState > 0 ? "SUPPORTED" : rootState < 0 ? "REFUTED" : "INSUFFICIENT";
  return {
    scoring_method: "EVIDENCE_NODE_MATRIX_V2",
    logic_graph_version: graph.graph_version,
    previous_score: healthScore,
    health_score: healthScore,
    score_delta: 0,
    root_support_strength: Math.max(0, rootState),
    root_contradict_strength: Math.max(0, -rootState),
    root_state: rootState,
    root_verdict: rootVerdict,
    coverage_percent: 0,
    invalidation_policy_version: "2.0.0",
    is_broken: false,
    invalidated_assumptions: [],
    assumption_scores: [],
    node_scores: graph.nodes.map((node) => ({
      node_id: node.node_id,
      label: node.label,
      kind: node.kind,
      operator: node.operator,
      support_strength: node.node_id === graph.root_id ? Math.max(0, rootState) : 0,
      contradict_strength: node.node_id === graph.root_id ? Math.max(0, -rootState) : 0,
      state: node.node_id === graph.root_id ? rootState : 0,
      verdict: node.node_id === graph.root_id ? rootVerdict : "INSUFFICIENT",
      coverage_percent: 0,
      required: false,
    })),
    evidence_impacts: [],
  };
}

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

const nvdaGraph = mockLogicGraph(
  "NVIDIA는 AI 학습·추론 인프라의 표준 지위를 바탕으로 데이터센터 매출 성장을 지속한다.",
  ["하이퍼스케일러 AI CAPEX가 성장한다", "CUDA 전환 비용이 높게 유지된다"],
);

const nvdaThesis: Thesis = {
  id: "30000000-0000-4000-8000-000000000001",
  holding_id: "20000000-0000-4000-8000-000000000001",
  raw_input: "AI 데이터센터 투자 확대가 이어지고 CUDA 생태계가 NVIDIA의 지위를 지킬 것이다.",
  main_thesis: "NVIDIA는 AI 학습·추론 인프라의 표준 지위를 바탕으로 데이터센터 매출 성장을 지속한다.",
  key_assumptions: ["하이퍼스케일러 AI CAPEX가 성장한다", "CUDA 전환 비용이 높게 유지된다"],
  positive_signals: ["클라우드 사업자 가이던스 상향", "차세대 GPU 수요 증가"],
  negative_signals: ["고객사 자체 ASIC 확대", "데이터센터 투자 효율화"],
  key_risks: ["수출 규제 강화", "대형 고객 매출 집중"],
  logic_graph: nvdaGraph,
  score_breakdown: mockScoreBreakdown(nvdaGraph, 32),
  confidence_score: 32,
  status: "STRENGTHENED",
  created_at: "2026-03-02T09:00:00Z",
  updated_at: now,
};

const avgoGraph = mockLogicGraph(
  "Broadcom은 Custom AI ASIC과 네트워크 칩 수요 증가로 성장한다.",
  ["주요 고객의 Custom ASIC 물량이 증가한다"],
);

const avgoThesis: Thesis = {
  id: "30000000-0000-4000-8000-000000000002",
  holding_id: "20000000-0000-4000-8000-000000000002",
  raw_input: "Custom AI ASIC과 네트워크 수요가 Broadcom의 성장을 견인할 것이다.",
  main_thesis: "Broadcom은 Custom AI ASIC과 네트워크 칩 수요 증가로 성장한다.",
  key_assumptions: ["주요 고객의 Custom ASIC 물량이 증가한다"],
  positive_signals: ["AI 반도체 수주 확대"],
  negative_signals: ["고객사 발주 지연"],
  key_risks: ["소수 고객 의존도"],
  logic_graph: avgoGraph,
  score_breakdown: mockScoreBreakdown(avgoGraph, 4),
  confidence_score: 4,
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

const mockThesisVersions: Record<string, ThesisVersion[]> = {};

const mockPrices: Record<string, number> = { NVDA: 171.32, AVGO: 291.48, TSM: 246.15 };

let dashboardState: PortfolioDashboard = {
  portfolio: mockPortfolios[0],
  holdings,
  concentration,
  common_risks: [],
  recent_alerts: alerts,
};

function refreshMockWeights() {
  const marketValues = dashboardState.holdings.map((holding) => ({
    id: holding.id,
    value: Math.max(0, holding.quantity) * (mockPrices[holding.ticker] ?? 100),
  }));
  const total = marketValues.reduce((sum, item) => sum + item.value, 0);
  const investableRatio = Math.max(0, 100 - dashboardState.portfolio.cash_ratio);
  const weights = new Map(marketValues.map((item) => [
    item.id,
    total > 0 ? Math.round((item.value / total * investableRatio) * 100) / 100 : 0,
  ]));
  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((holding) => ({
      ...holding,
      current_weight: weights.get(holding.id) ?? 0,
    })),
  };
}

export function getMockDashboard(): PortfolioDashboard {
  refreshMockWeights();
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
    avg_buy_price: 0,
    target_weight: 0,
    current_weight: 0,
    created_at: createdAt,
    updated_at: createdAt,
    thesis: null,
    latest_change: null,
  };
  dashboardState = {
    ...dashboardState,
    holdings: [holding, ...dashboardState.holdings],
  };
  refreshMockWeights();
  return structuredClone(
    dashboardState.holdings.find((item) => item.id === holding.id) ?? holding,
  );
}

export function removeMockHolding(holdingId: string): void {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding) throw new Error("삭제할 보유 종목을 찾을 수 없습니다.");

  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.filter((item) => item.id !== holdingId),
    concentration: dashboardState.concentration
      ? {
          ...dashboardState.concentration,
          affected_holdings: dashboardState.concentration.affected_holdings?.filter(
            (ticker) => ticker !== holding.ticker,
          ) ?? [],
        }
      : null,
  };
}

export function removeMockAlert(alertId: string): void {
  const alert = dashboardState.recent_alerts.find((item) => item.id === alertId);
  if (!alert) throw new Error("삭제할 알림을 찾을 수 없습니다.");

  dashboardState = {
    ...dashboardState,
    recent_alerts: dashboardState.recent_alerts.filter((item) => item.id !== alertId),
  };
}

export function updateMockHoldingWeight(
  holdingId: string,
  currentWeight: number,
): DashboardHolding {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding) throw new Error("수정할 보유 종목을 찾을 수 없습니다.");
  const updated = {
    ...holding,
    current_weight: currentWeight,
    updated_at: new Date().toISOString(),
  };
  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((item) => item.id === holdingId ? updated : item),
  };
  return structuredClone(updated);
}

export function updateMockHoldingPosition(
  holdingId: string,
  input: UpdateHoldingPositionInput,
): DashboardHolding {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding) throw new Error("수정할 보유 종목을 찾을 수 없습니다.");
  const updated = { ...holding, ...input, updated_at: new Date().toISOString() };
  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((item) => item.id === holdingId ? updated : item),
  };
  refreshMockWeights();
  return structuredClone(
    dashboardState.holdings.find((item) => item.id === holdingId) ?? updated,
  );
}

export function getMockMarketSnapshot(ticker: string): MarketSnapshot {
  const currentPrice = mockPrices[ticker] ?? 100;
  return {
    ticker,
    current_price: currentPrice,
    change_pct_30d: ticker === "AVGO" ? -2.4 : 6.8,
    as_of: new Date().toISOString().slice(0, 10),
    day_open: currentPrice * 0.99,
    day_high: currentPrice * 1.018,
    day_low: currentPrice * 0.982,
    volume: 42_810_000,
  };
}

export function createMockThesis(holdingId: string, rawInput: string): Thesis {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding) throw new Error("보유 종목을 찾을 수 없습니다.");
  const createdAt = new Date().toISOString();
  const assumptions = ["산업 수요가 투자 기간 동안 성장한다"];
  const graph = mockLogicGraph(rawInput, assumptions);
  const thesis: Thesis = {
    id: crypto.randomUUID(),
    holding_id: holdingId,
    raw_input: rawInput,
    main_thesis: rawInput,
    key_assumptions: assumptions,
    positive_signals: ["수요 가이던스 상향"],
    negative_signals: ["예상보다 느린 수요 회복"],
    key_risks: ["산업 사이클 변동성"],
    logic_graph: graph,
    score_breakdown: mockScoreBreakdown(graph, 0),
    confidence_score: 0,
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

export function updateMockThesis(thesisId: string, rawInput: string): Thesis {
  const holding = dashboardState.holdings.find((item) => item.thesis?.id === thesisId);
  if (!holding?.thesis) throw new Error("수정할 투자 논리를 찾을 수 없습니다.");
  const assumptions = ["수정된 투자 논리의 핵심 전제가 유지된다"];
  const graph = mockLogicGraph(rawInput, assumptions);
  const thesis: Thesis = {
    ...holding.thesis,
    raw_input: rawInput,
    main_thesis: rawInput,
    key_assumptions: assumptions,
    positive_signals: ["핵심 전제를 뒷받침하는 신규 근거"],
    negative_signals: ["핵심 전제를 약화하는 반대 근거"],
    key_risks: ["수정된 핵심 전제가 성립하지 않을 가능성"],
    logic_graph: graph,
    score_breakdown: mockScoreBreakdown(graph, 0),
    confidence_score: 0,
    status: "UNCHANGED",
    updated_at: new Date().toISOString(),
  };
  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((item) =>
      item.id === holding.id ? { ...item, thesis } : item,
    ),
  };
  return structuredClone(thesis);
}

export function updateMockThesisLogicOperator(
  thesisId: string,
  nodeId: string,
  operator: LogicOperator,
): Thesis {
  const holding = dashboardState.holdings.find((item) => item.thesis?.id === thesisId);
  if (!holding?.thesis?.logic_graph) throw new Error("변경할 논리 그래프를 찾을 수 없습니다.");

  const target = holding.thesis.logic_graph.nodes.find((node) => node.node_id === nodeId);
  if (!target || target.kind !== "CLAIM" || target.child_ids.length === 0) {
    throw new Error("하위 노드를 연결하는 CLAIM 노드만 변경할 수 있습니다.");
  }

  const graph = {
    ...holding.thesis.logic_graph,
    nodes: holding.thesis.logic_graph.nodes.map((node) =>
      node.node_id === nodeId ? { ...node, operator } : node,
    ),
  };
  const thesis: Thesis = {
    ...holding.thesis,
    logic_graph: graph,
    score_breakdown: mockScoreBreakdown(graph, 0),
    confidence_score: 0,
    status: "UNCHANGED",
    updated_at: new Date().toISOString(),
  };
  dashboardState = {
    ...dashboardState,
    holdings: dashboardState.holdings.map((item) =>
      item.id === holding.id ? { ...item, thesis } : item,
    ),
  };
  return structuredClone(thesis);
}

export function runMockAnalysis(holdingId: string): HoldingAnalysisResponse {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding?.thesis) throw new Error("분석할 Thesis가 없습니다.");

  const updatedThesis: Thesis = {
    ...holding.thesis,
    confidence_score: Math.min(50, holding.thesis.confidence_score + 6),
    score_breakdown: holding.thesis.score_breakdown
      ? {
          ...holding.thesis.score_breakdown,
          previous_score: holding.thesis.confidence_score,
          health_score: Math.min(50, holding.thesis.confidence_score + 6),
          score_delta: 6,
        }
      : null,
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
    snapshot: holding.thesis,
    created_at: updatedThesis.updated_at,
  };
  mockThesisVersions[updatedThesis.id] = [
    version,
    ...(mockThesisVersions[updatedThesis.id] ?? []),
  ];
  const evidence: Evidence[] = [
    {
      id: crypto.randomUUID(),
      thesis_id: updatedThesis.id,
      document_id: "earnings-mock-001",
      source_type: "EARNINGS",
      source_url: "https://example.com/earnings",
      vector_doc_id: "earnings-mock-001",
      content_snippet: "주요 고객의 AI 인프라 주문이 전 분기 대비 증가했습니다.",
      classification: "SUPPORT",
      impact: "HIGH",
      reason: "AI CAPEX 성장 전제를 직접 지지합니다.",
      related_assumptions: [updatedThesis.key_assumptions[0]],
      assumption_findings: [{
        assumption: updatedThesis.key_assumptions[0],
        assessment: "SUPPORT",
        impact: "HIGH",
        relevance_score: 1,
        reasoning: "AI CAPEX 성장 전제를 직접 지지합니다.",
        source_passage_indices: [0],
      }],
      score_delta: 6,
      node_contributions: [{
        node_id: "assumption_1",
        assumption: updatedThesis.key_assumptions[0],
        assessment: "SUPPORT",
        impact: "HIGH",
        relevance_score: 1,
        signed_strength: 1,
      }],
      evidence_scope: "NEW",
      published_at: updatedThesis.updated_at,
      saved_to_history: true,
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
  const alert: Alert = {
    id: crypto.randomUUID(),
    user_id: userId,
    portfolio_id: dashboardState.portfolio.id,
    thesis_id: updatedThesis.id,
    severity: "MAJOR",
    title: `[MAJOR] ${holding.ticker} 투자 논리 변동 감지`,
    message: `${version.change_reason} 등록된 이메일로 변경 요약과 근거 링크를 발송했습니다.`,
    is_sent: true,
    sent_at: updatedThesis.updated_at,
    created_at: updatedThesis.updated_at,
  };

  // 수동 재분석(mock)이므로 alert는 응답에만 담아 반환하고, 자동 재분석 알림만
  // 노출되는 recent_alerts 목록에는 추가하지 않는다.
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
    alert,
  });
}

export function getMockThesisHistory(thesisId: string): ThesisVersion[] {
  return structuredClone(mockThesisVersions[thesisId] ?? []);
}

export function getMockHoldingHistory(holdingId: string): HoldingHistoryResponse {
  const holding = dashboardState.holdings.find((item) => item.id === holdingId);
  if (!holding?.thesis) throw new Error("투자 논리가 등록된 종목만 History를 조회할 수 있습니다.");
  return {
    holding_id: holding.id,
    ticker: holding.ticker,
    thesis: structuredClone(holding.thesis),
    entries: [],
    total_count: 0,
  };
}

export function getMockPortfolioQuery(question: string): PortfolioQueryResponse {
  const trimmed = question.trim();
  const holdingsWithThesis = dashboardState.holdings.filter((item) => item.thesis);
  const nvda = dashboardState.holdings.find((item) => item.ticker === "NVDA");
  const avgo = dashboardState.holdings.find((item) => item.ticker === "AVGO");
  const tsm = dashboardState.holdings.find((item) => item.ticker === "TSM");

  const baseScope: PortfolioQueryScope = {
    holding_count: dashboardState.holdings.length,
    thesis_count: holdingsWithThesis.length,
    candidate_evidence_count: 12,
    selected_evidence_count: 0,
    latest_evidence_at: now,
  };

  const respond = (
    answer: string,
    evidence: PortfolioQueryEvidence[],
    limitations: string[],
  ): PortfolioQueryResponse => structuredClone({
    answer,
    evidence_document_ids: evidence.map((item) => item.document_id),
    evidence,
    limitations,
    scope: { ...baseScope, selected_evidence_count: evidence.length },
  });

  if (/공통|의존|가정/.test(trimmed) && nvda?.thesis && avgo?.thesis) {
    return respond(
      "NVDA와 AVGO 모두 '하이퍼스케일러 AI CAPEX 성장'이라는 공통 가정에 크게 의존하고 있습니다. 이 가정이 꺾이면 두 종목의 투자 논리가 동시에 흔들릴 수 있습니다.",
      [
        {
          document_id: "macro-mock-capex-01",
          holding_id: nvda.id,
          ticker: nvda.ticker,
          content_snippet: "하이퍼스케일러 4사의 2026년 AI 데이터센터 CAPEX 가이던스가 전년 대비 상향 조정되었습니다.",
          source_url: "https://example.com/macro/capex-guidance",
          published_at: now,
          classification: "SUPPORT",
          impact: "HIGH",
          related_assumptions: [nvda.thesis.key_assumptions[0]],
        },
        {
          document_id: "earnings-mock-avgo-01",
          holding_id: avgo.id,
          ticker: avgo.ticker,
          content_snippet: "Broadcom의 Custom AI ASIC 수주 잔고가 하이퍼스케일러 CAPEX 확대와 함께 증가했습니다.",
          source_url: "https://example.com/earnings/avgo-q2",
          published_at: now,
          classification: "SUPPORT",
          impact: "MEDIUM",
          related_assumptions: avgo.thesis.key_assumptions,
        },
      ],
      ["근거는 질문과의 의미적 관련성이 아니라 최신순으로만 선택했습니다."],
    );
  }

  if (/위험|리스크/.test(trimmed) && avgo?.thesis) {
    return respond(
      "가장 최근 근거 기준으로는 AVGO의 고객사 발주 지연 이슈가 여러 종목에 영향을 줄 수 있는 공통 리스크로 보입니다. NVDA·TSM에서는 아직 동일한 신호가 확인되지 않았습니다.",
      [
        {
          document_id: "news-mock-avgo-risk-01",
          holding_id: avgo.id,
          ticker: avgo.ticker,
          content_snippet: "주요 고객사가 일부 발주를 다음 분기로 연기했다는 보도가 나왔습니다.",
          source_url: "https://example.com/news/avgo-delay",
          published_at: now,
          classification: "CONTRADICT",
          impact: "MEDIUM",
          related_assumptions: avgo.thesis.key_assumptions,
        },
      ],
      [
        "근거는 질문과의 의미적 관련성이 아니라 최신순으로만 선택했습니다.",
        "일부 종목은 근거가 없어 이번 답변에 반영되지 않았을 수 있습니다.",
      ],
    );
  }

  if (/부족|약한|약해/.test(trimmed)) {
    return respond(
      tsm
        ? `${tsm.ticker}는 아직 투자 논리(Thesis)가 등록되지 않아 평가할 근거 자체가 없습니다. 등록된 Thesis 중에서는 AVGO의 근거가 가장 얇습니다.`
        : "등록된 Thesis 중 근거가 가장 부족한 종목을 찾지 못했습니다.",
      [],
      [
        "포트폴리오에 저장된 근거가 아직 없습니다.",
        "아직 투자 논리(Thesis)가 등록되지 않은 종목은 이번 답변에 반영되지 않았습니다.",
      ],
    );
  }

  return respond(
    "질문과 직접 관련된 근거를 찾지 못했습니다. 질문을 더 구체적으로 입력하시거나, 추천 질문을 사용해 보세요.",
    [],
    ["질문과 직접 관련된 저장 근거를 찾지 못했습니다."],
  );
}

// -------------------------------------------------------------- Admin mock
let mockAppSettings: AppSetting[] = [
  { key: "scoring.impact_weight_low", category: "scoring", value: 0.09, description: "LOW-impact evidence의 신호 강도 가중치", updated_by_id: null, updated_at: now },
  { key: "scoring.impact_weight_medium", category: "scoring", value: 0.27, description: "MEDIUM-impact evidence의 신호 강도 가중치", updated_by_id: null, updated_at: now },
  { key: "scoring.impact_weight_high", category: "scoring", value: 0.54, description: "HIGH-impact evidence의 신호 강도 가중치", updated_by_id: null, updated_at: now },
  { key: "scoring.invalidation_streak_required", category: "scoring", value: 2, description: "논리 무효화(BROKEN) 판정에 필요한 연속 반박 근거 횟수", updated_by_id: null, updated_at: now },
  { key: "policy.major_movement_threshold", category: "policy", value: -2, description: "MAJOR 알림으로 분류되는 상태 하락 폭", updated_by_id: null, updated_at: now },
  { key: "scheduler.max_retries", category: "scheduler", value: 2, description: "예약 재분석 실패 시 최대 재시도 횟수", updated_by_id: null, updated_at: now },
  { key: "scheduler.retry_delay_minutes_first", category: "scheduler", value: 5, description: "첫 번째 재시도까지 대기 시간(분)", updated_by_id: null, updated_at: now },
  { key: "scheduler.retry_delay_minutes_second", category: "scheduler", value: 15, description: "두 번째 재시도까지 대기 시간(분)", updated_by_id: null, updated_at: now },
  { key: "scheduler.stale_threshold_hours", category: "scheduler", value: 12, description: "이 시간을 넘긴 예약은 건너뛰고 SKIPPED 처리", updated_by_id: null, updated_at: now },
  { key: "scheduler.poll_seconds", category: "scheduler", value: 60, description: "스케줄러가 예약 목록을 확인하는 주기(초)", updated_by_id: null, updated_at: now },
  { key: "scheduler.min_confidence_delta_for_alert", category: "scheduler", value: 5, description: "예약 재분석에서 알림을 보낼 최소 신뢰도 변동폭", updated_by_id: null, updated_at: now },
  { key: "llm.temperature", category: "llm", value: 0, description: "분석에 사용하는 LLM temperature", updated_by_id: null, updated_at: now },
  { key: "llm.timeout_seconds", category: "llm", value: 30, description: "LLM 호출 타임아웃(초)", updated_by_id: null, updated_at: now },
  { key: "llm.max_retries", category: "llm", value: 1, description: "LLM 호출 실패 시 재시도 횟수", updated_by_id: null, updated_at: now },
  { key: "rag.dense_candidate_ratio", category: "rag", value: 0.2, description: "하이브리드 RAG에서 dense 검색이 차지하는 후보 비율", updated_by_id: null, updated_at: now },
  { key: "qa.evidence_limit", category: "qa", value: 50, description: "포트폴리오 질의에 사용하는 최근 Evidence 최대 개수", updated_by_id: null, updated_at: now },
];

export function getMockAppSettings(): AppSetting[] {
  return structuredClone(mockAppSettings);
}

export function updateMockAppSetting(key: string, value: AppSetting["value"]): AppSetting {
  mockAppSettings = mockAppSettings.map((setting) =>
    setting.key === key ? { ...setting, value, updated_at: new Date().toISOString() } : setting,
  );
  const updated = mockAppSettings.find((setting) => setting.key === key);
  if (!updated) throw new Error(`알 수 없는 설정 키입니다: ${key}`);
  return structuredClone(updated);
}

export function getMockAdminSchedules(): AdminScheduleOverview[] {
  return [
    {
      schedule_id: "mock-schedule-1",
      holding_id: "20000000-0000-4000-8000-000000000001",
      ticker: "NVDA",
      user_email: "demo@thesisguard.local",
      enabled: true,
      next_run_at: new Date(Date.now() + 3600_000).toISOString(),
      last_run_at: now,
      latest_run_status: "SUCCEEDED",
      latest_run_error: null,
    },
    {
      schedule_id: "mock-schedule-2",
      holding_id: "20000000-0000-4000-8000-000000000002",
      ticker: "AVGO",
      user_email: "demo@thesisguard.local",
      enabled: true,
      next_run_at: new Date(Date.now() + 7200_000).toISOString(),
      last_run_at: null,
      latest_run_status: "FAILED",
      latest_run_error: "LLM 요청이 타임아웃되었습니다.",
    },
  ];
}

export function getMockAdminHealth(): AdminHealth {
  return {
    database: "ok",
    llm_provider: "openai",
    rag_enabled: true,
    langfuse: "disabled",
    langfuse_base_url: "https://cloud.langfuse.com",
    scheduler_enabled: true,
    scheduler_poll_seconds: 60,
  };
}

export function getMockLangfuseTraces(): LangfuseTrace[] {
  return [
    {
      id: "mock-trace-1",
      name: "thesisguard.analyze-holding",
      timestamp: now,
      user_id: userId,
      latency_seconds: 4.82,
      total_cost: 0.0123,
      tags: ["thesisguard"],
    },
    {
      id: "mock-trace-2",
      name: "thesisguard.portfolio-query",
      timestamp: now,
      user_id: userId,
      latency_seconds: 1.94,
      total_cost: 0.0041,
      tags: ["thesisguard"],
    },
  ];
}

let mockQaLogs: QaLogEntry[] = [
  {
    id: "mock-qa-1",
    user_id: userId,
    user_email: "demo@thesisguard.local",
    portfolio_id: portfolioId,
    question: "포트폴리오에서 가장 위험한 종목은?",
    answer: "가장 최근 근거 기준으로는 AVGO의 고객사 발주 지연 이슈가 공통 리스크로 보입니다.",
    evidence_document_ids: ["news-mock-avgo-risk-01"],
    created_at: now,
  },
];

export function getMockQaLogs(): QaLogEntry[] {
  return structuredClone(mockQaLogs);
}

export function addMockQaLog(question: string, answer: string): void {
  mockQaLogs = [
    {
      id: `mock-qa-${mockQaLogs.length + 1}`,
      user_id: userId,
      user_email: "demo@thesisguard.local",
      portfolio_id: portfolioId,
      question,
      answer,
      evidence_document_ids: [],
      created_at: new Date().toISOString(),
    },
    ...mockQaLogs,
  ];
}

let mockEvalScenarios: EvalScenario[] = [
  {
    id: "mock-scenario-1",
    name: "NVDA capex 질문",
    category: "portfolio_qa",
    question: "NVDA 투자 논리를 뒷받침하는 최근 근거는?",
    context_snapshot: {},
    expected_document_ids: [],
    required_keywords: ["최신순"],
    forbidden_terms: ["투자 권유"],
    is_active: true,
    created_at: now,
    updated_at: now,
  },
];

export function getMockEvalScenarios(): EvalScenario[] {
  return structuredClone(mockEvalScenarios);
}

export function addMockEvalScenario(input: EvalScenarioInput): EvalScenario {
  const scenario: EvalScenario = {
    id: `mock-scenario-${mockEvalScenarios.length + 1}`,
    ...input,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  mockEvalScenarios = [scenario, ...mockEvalScenarios];
  return structuredClone(scenario);
}

export function runMockEvalScenario(scenarioId: string): EvalRun {
  const scenario = mockEvalScenarios.find((item) => item.id === scenarioId);
  return {
    id: `mock-run-${Date.now()}`,
    scenario_id: scenarioId,
    settings_snapshot: Object.fromEntries(mockAppSettings.map((s) => [s.key, s.value])),
    metrics: {
      citation_precision: 1,
      citation_recall: scenario ? 0.8 : 0,
      limitation_recall: 1,
      forbidden_term_hits: 0,
      answer: "(mock) 시나리오 실행 결과 예시 답변입니다.",
    },
    status: "SUCCEEDED",
    error_message: null,
    created_at: new Date().toISOString(),
  };
}
