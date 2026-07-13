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
export type AlertSeverity = "CRITICAL" | "MAJOR" | "MINOR" | "NONE";
export type AnalysisType = "BULL_BEAR_JUDGE" | "THESIS_CONCENTRATION" | "COMMON_RISK";

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
  avg_buy_price: number;
  target_weight: number;
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
  source_type: EvidenceSourceType;
  source_url: string | null;
  vector_doc_id: string | null;
  content_snippet: string;
  classification: EvidenceClassification;
  impact: EvidenceImpact;
  reason: string;
  published_at: string | null;
  created_at: string;
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
