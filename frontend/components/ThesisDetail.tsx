"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import type { DashboardHolding, HoldingAnalysisResponse } from "@/types/schema";

interface ThesisDetailProps {
  holding: DashboardHolding;
  analysis: HoldingAnalysisResponse | null;
  analyzing: boolean;
  onAnalyze: () => void;
  onRegister: (rawInput: string) => Promise<void>;
}

export function ThesisDetail({ holding, analysis, analyzing, onAnalyze, onRegister }: ThesisDetailProps) {
  const [rawInput, setRawInput] = useState("");
  const [registering, setRegistering] = useState(false);
  const thesis = analysis?.thesis ?? holding.thesis;
  if (!thesis) {
    return (
      <section className="panel thesis-detail empty-thesis">
        <span className="section-index">04</span>
        <h2>{holding.ticker} Thesis</h2>
        <p>매수 이유를 자연어로 입력하면 핵심 전제·신호·리스크로 구조화합니다.</p>
        <textarea
          aria-label="투자 논리 원문"
          onChange={(event) => setRawInput(event.target.value)}
          placeholder="예: AI 반도체 수요 증가와 파운드리 경쟁력을 바탕으로 장기 성장할 것이다."
          value={rawInput}
        />
        <button
          className="primary-button"
          disabled={registering || rawInput.trim().length < 10}
          onClick={async () => {
            setRegistering(true);
            try {
              await onRegister(rawInput.trim());
            } finally {
              setRegistering(false);
            }
          }}
          type="button"
        >
          {registering ? "Thesis 구조화 중…" : "투자 논리 등록"}
        </button>
      </section>
    );
  }

  return (
    <section className="panel thesis-detail">
      <div className="thesis-title-row">
        <div>
          <span className="section-index">04</span>
          <p className="kicker">{holding.ticker} / CURRENT THESIS</p>
          <h2>{thesis.main_thesis}</h2>
        </div>
        <div className="confidence-hero">
          <span>CONFIDENCE</span>
          <strong>{thesis.confidence_score}</strong>
          <StatusBadge status={thesis.status} />
        </div>
      </div>

      <div className="thesis-grid">
        <DetailList title="핵심 전제" items={thesis.key_assumptions} />
        <DetailList title="긍정 신호" items={thesis.positive_signals} tone="positive" />
        <DetailList title="부정 신호" items={thesis.negative_signals} tone="negative" />
        <DetailList title="주요 리스크" items={thesis.key_risks} tone="risk" />
      </div>

      {analysis && (
        <div className="analysis-result">
          <div>
            <span className="result-label">JUDGE</span>
            <p>{analysis.analysis_result.judge_summary}</p>
          </div>
          <div>
            <span className="result-label">CHANGE</span>
            <p>{analysis.version.change_reason}</p>
          </div>
          {analysis.evidence.map((evidence) => (
            <a href={evidence.source_url ?? undefined} key={evidence.id} rel="noreferrer" target="_blank">
              <span>{evidence.classification} · {evidence.impact}</span>
              {evidence.content_snippet}
            </a>
          ))}
        </div>
      )}

      <div className="thesis-actions">
        <p>모든 분석 결과는 근거 URL과 원문 발췌를 동반합니다.</p>
        <button className="primary-button" disabled={analyzing} onClick={onAnalyze} type="button">
          {analyzing ? "분석 파이프라인 실행 중…" : "신규 정보로 재분석"}
        </button>
      </div>
    </section>
  );
}

function DetailList({
  title,
  items,
  tone = "default",
}: {
  title: string;
  items: string[];
  tone?: "default" | "positive" | "negative" | "risk";
}) {
  return (
    <div className={`detail-list detail-list--${tone}`}>
      <h3>{title}</h3>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}
