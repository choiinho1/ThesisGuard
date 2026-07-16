export type ApiMode = "mock" | "live";

export type UserRole = "user" | "admin";

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  role: UserRole;
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
export type LogicOperator = "AND" | "OR" | "CONTRIBUTING";
export type AssumptionAssessment = "SUPPORT" | "CONTRADICT" | "MIXED" | "NOT_ADDRESSED";
export type NodeEvidenceVerdict =
  | "SUPPORTED"
  | "REFUTED"
  | "CONFLICTING"
  | "INSUFFICIENT";

export interface AssumptionFinding {
  assumption: string;
  assessment: AssumptionAssessment;
  impact: EvidenceImpact;
  relevance_score: number;
  reasoning: string;
  source_passage_indices: number[];
}

export interface ThesisLogicNode {
  node_id: string;
  kind: "CLAIM" | "ASSUMPTION";
  label: string;
  operator: LogicOperator | null;
  child_ids: string[];
  assumption: string | null;
}

export interface ThesisLogicGraph {
  graph_version: string;
  root_id: string;
  nodes: ThesisLogicNode[];
}

export interface AssumptionScoreState {
  assumption: string;
  node_id: string;
  support_strength: number;
  contradict_strength: number;
  state: number;
  verdict: NodeEvidenceVerdict;
  has_evidence: boolean;
  evidence_document_ids: string[];
  evidence_event_keys: string[];
  invalidation_streak: number;
  invalidation_triggered: boolean;
}

export interface LogicNodeScore {
  node_id: string;
  label: string;
  kind: "CLAIM" | "ASSUMPTION";
  operator: LogicOperator | null;
  support_strength: number;
  contradict_strength: number;
  state: number;
  verdict: NodeEvidenceVerdict;
  coverage_percent: number;
  required: boolean;
}

export interface EvidenceNodeContribution {
  node_id: string;
  assumption: string;
  assessment: AssumptionAssessment;
  impact: EvidenceImpact;
  relevance_score: number;
  signed_strength: number;
}

export interface EvidenceScoreImpact {
  document_id: string;
  score_delta: number;
  node_contributions: EvidenceNodeContribution[];
}

export interface ThesisScoreBreakdown {
  scoring_method: "EVIDENCE_NODE_MATRIX_V2";
  logic_graph_version: string;
  previous_score: number;
  health_score: number;
  score_delta: number;
  root_support_strength: number;
  root_contradict_strength: number;
  root_state: number;
  root_verdict: NodeEvidenceVerdict;
  coverage_percent: number;
  invalidation_policy_version: string;
  is_broken: boolean;
  invalidated_assumptions: string[];
  assumption_scores: AssumptionScoreState[];
  node_scores: LogicNodeScore[];
  evidence_impacts: EvidenceScoreImpact[];
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

export interface TickerQuote {
  symbol: string;
  price: number | null;
  change_pct: number | null;
  as_of: string | null;
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
  logic_graph: ThesisLogicGraph | null;
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
  related_assumptions: string[];
  assumption_findings: AssumptionFinding[];
  score_delta: number;
  node_contributions: EvidenceNodeContribution[];
  evidence_scope: EvidenceScope;
  published_at: string | null;
  saved_to_history: boolean;
  created_at: string;
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

export interface PortfolioQueryRequest {
  question: string;
}

export interface PortfolioQueryEvidence {
  document_id: string;
  holding_id: string;
  ticker: string;
  content_snippet: string;
  source_url: string | null;
  published_at: string | null;
  classification: EvidenceClassification;
  impact: EvidenceImpact;
  related_assumptions: string[];
}

export interface PortfolioQueryScope {
  holding_count: number;
  thesis_count: number;
  candidate_evidence_count: number;
  selected_evidence_count: number;
  latest_evidence_at: string | null;
}

export interface PortfolioQueryResponse {
  answer: string;
  // Kept for backward compat with older backends; prefer `evidence` — a raw
  // document_id alone has no ticker/snippet/source to render.
  evidence_document_ids: string[];
  evidence: PortfolioQueryEvidence[];
  limitations: string[];
  scope: PortfolioQueryScope;
}

// ------------------------------------------------------------------ Admin
export interface AppSetting {
  key: string;
  category: string;
  value: number | string | boolean;
  description: string | null;
  updated_by_id: string | null;
  updated_at: string;
}

export interface AdminScheduleOverview {
  schedule_id: string;
  holding_id: string;
  ticker: string;
  user_email: string;
  enabled: boolean;
  next_run_at: string;
  last_run_at: string | null;
  latest_run_status: string | null;
  latest_run_error: string | null;
}

export interface AdminHealth {
  database: string;
  llm_provider: string;
  rag_enabled: boolean;
  langfuse: string;
  langfuse_base_url: string;
  scheduler_enabled: boolean;
  scheduler_poll_seconds: number;
}

export interface LangfuseTrace {
  id: string;
  name: string | null;
  timestamp: string | null;
  user_id: string | null;
  latency_seconds: number | null;
  total_cost: number | null;
  tags: string[];
}

export interface QaLogEntry {
  id: string;
  user_id: string;
  user_email: string;
  portfolio_id: string;
  question: string;
  answer: string;
  evidence_document_ids: string[];
  created_at: string;
}

export interface EvalScenarioInput {
  name: string;
  category: string;
  question: string;
  context_snapshot: Record<string, unknown>;
  expected_document_ids: string[];
  required_keywords: string[];
  forbidden_terms: string[];
  is_active: boolean;
}

export interface EvalScenario {
  id: string;
  name: string;
  category: string;
  question: string;
  context_snapshot: Record<string, unknown>;
  expected_document_ids: string[];
  required_keywords: string[];
  forbidden_terms: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EvalRun {
  id: string;
  scenario_id: string | null;
  settings_snapshot: Record<string, unknown>;
  metrics: Record<string, unknown>;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";
  error_message: string | null;
  created_at: string;
}
