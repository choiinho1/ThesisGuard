export type ApiMode = "mock" | "live";

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface SignupInput extends LoginInput {
  name?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export type EvidenceClassification =
  | "SUPPORT"
  | "CONTRADICT"
  | "NEUTRAL"
  | "UNCERTAIN";

export type ThesisStatus =
  | "STRONGLY_STRENGTHENED"
  | "STRENGTHENED"
  | "UNCHANGED"
  | "WEAKENED"
  | "STRONGLY_WEAKENED"
  | "BROKEN";

export type EvidenceImpact = "HIGH" | "MEDIUM" | "LOW";
export type EvidenceSourceType = "SEC_FILING" | "IR" | "EARNINGS" | "NEWS" | "MACRO";
export type EvidenceScope = "NEW" | "PAST";
export type AlertSeverity = "CRITICAL" | "MAJOR" | "MINOR" | "NONE";
export type AnalysisType = "BULL_BEAR_JUDGE" | "THESIS_CONCENTRATION" | "COMMON_RISK";
export type ThesisTemplateId =
  | "GENERAL_FUNDAMENTAL"
  | "SCALABLE_GROWTH"
  | "QUALITY_COMPOUNDER"
  | "MARGIN_EXPANSION"
  | "TURNAROUND"
  | "CYCLICAL_RECOVERY"
  | "CATALYST_EVENT"
  | "ASSET_VALUE_RERATING"
  | "INCOME_DISTRIBUTION";

export interface AssumptionBinding {
  slot_id: string;
  assumptions: string[];
  mapping_reason: string;
}

export interface AssumptionScoreState {
  assumption: string;
  slot_id: string;
  support_strength: 0 | 0.5 | 1;
  contradict_strength: 0 | 0.5 | 1;
  state: -1 | -0.5 | 0 | 0.5 | 1;
  has_evidence: boolean;
  evidence_document_ids: string[];
  invalidation_streak: number;
  invalidation_triggered: boolean;
}

export interface SlotScore {
  slot_id: string;
  label_ko: string;
  weight_bps: number;
  core: boolean;
  state: number;
  contribution_points: number;
  coverage_percent: number;
}

export interface ThesisScoreBreakdown {
  template_id: ThesisTemplateId;
  template_catalog_version: string;
  previous_score: number;
  health_score: number;
  score_delta: number;
  coverage_percent: number;
  invalidation_policy_version: string;
  is_broken: boolean;
  invalidated_assumptions: string[];
  assumption_scores: AssumptionScoreState[];
  slot_scores: SlotScore[];
}

export interface Portfolio {
  id: string;
  user_id: string;
  name: string;
  investment_purpose: string;
  investment_horizon: string;
  cash_ratio: number;
  created_at: string;
  updated_at: string;
}

export interface Holding {
  id: string;
  portfolio_id: string;
  ticker: string;
  company_name: string;
  quantity: number;
  avg_buy_price: number;
  target_weight: number;
  current_weight: number;
  created_at: string;
  updated_at: string;
}

export interface CreateHoldingInput {
  ticker: string;
  company_name: string;
  quantity: number;
}

export interface UpdateHoldingPositionInput {
  quantity: number;
}

export interface MarketSnapshot {
  ticker: string;
  current_price: number | null;
  change_pct_30d: number | null;
  as_of: string | null;
  day_open: number | null;
  day_high: number | null;
  day_low: number | null;
  volume: number | null;
}

export interface Thesis {
  id: string;
  holding_id: string;
  raw_input: string;
  main_thesis: string;
  key_assumptions: string[];
  positive_signals: string[];
  negative_signals: string[];
  key_risks: string[];
  template_id: ThesisTemplateId;
  template_catalog_version: string;
  template_snapshot: Record<string, unknown>;
  assumption_bindings: AssumptionBinding[];
  score_breakdown: ThesisScoreBreakdown | null;
  confidence_score: number;
  status: ThesisStatus;
  created_at: string;
  updated_at: string;
}

export interface ThesisVersion {
  id: string;
  thesis_id: string;
  version_no: number;
  confidence_score: number;
  status: ThesisStatus;
  change_reason: string;
  conflicting_assumptions: string[];
  observation_points: string[];
  snapshot: Thesis;
  created_at: string;
}

export interface Evidence {
  id: string;
  thesis_id: string;
  document_id: string;
  source_type: EvidenceSourceType;
  source_url: string | null;
  vector_doc_id: string | null;
  content_snippet: string;
  classification: EvidenceClassification;
  impact: EvidenceImpact;
  reason: string;
  evidence_scope: EvidenceScope;
  published_at: string | null;
  saved_to_history: boolean;
  created_at: string;
}

export interface EvidenceHistoryEntry extends Evidence {
  holding_id: string;
  ticker: string;
}

export interface EvidenceHistoryGroup {
  holding_id: string;
  ticker: string;
  entries: Evidence[];
}

export interface AnalysisResult {
  id: string;
  portfolio_id: string | null;
  thesis_id: string | null;
  analysis_type: AnalysisType;
  bull_summary: string | null;
  bear_summary: string | null;
  judge_summary: string | null;
  concentration_theme: string | null;
  concentration_score: number | null;
  affected_holdings: string[] | null;
  raw_result: Record<string, unknown>;
  created_at: string;
}

export interface Alert {
  id: string;
  user_id: string;
  portfolio_id: string;
  thesis_id: string | null;
  severity: AlertSeverity;
  title: string;
  message: string;
  is_sent: boolean;
  sent_at: string | null;
  created_at: string;
}

export interface DashboardHolding extends Holding {
  thesis: Thesis | null;
  latest_change: ThesisVersion | null;
}

export interface PortfolioDashboard {
  portfolio: Portfolio;
  holdings: DashboardHolding[];
  concentration: AnalysisResult | null;
  common_risks: AnalysisResult[];
  recent_alerts: Alert[];
}

export interface HoldingAnalysisResponse {
  thesis: Thesis;
  version: ThesisVersion;
  evidence: Evidence[];
  analysis_result: AnalysisResult;
  alert: Alert | null;
}

export interface AnalysisScheduleInput {
  enabled: boolean;
  daily_time: string;
  timezone: string;
}

export interface AnalysisSchedule {
  id: string;
  holding_id: string;
  ticker: string;
  enabled: boolean;
  daily_time: string;
  timezone: string;
  recipient_email: string;
  last_run_at: string | null;
  last_run_status: string | null;
  next_run_at: string;
}

export interface HistoryEntry {
  version: ThesisVersion;
  analysis_result: AnalysisResult | null;
  evidence: Evidence[];
  alert: Alert | null;
}

export interface HoldingHistoryResponse {
  holding_id: string;
  ticker: string;
  thesis: Thesis;
  entries: HistoryEntry[];
  total_count: number;
}
