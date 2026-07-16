"use client";

import { FormEvent, KeyboardEvent, useId, useState } from "react";
import { queryPortfolio } from "@/lib/apiClient";
import type { ApiMode, PortfolioQueryEvidence, PortfolioQueryResponse } from "@/types/schema";

const MAX_QUESTION_LENGTH = 500;

const SUGGESTED_QUESTIONS = [
  "포트폴리오가 공통으로 의존하는 핵심 가정은 무엇인가요?",
  "최근 근거에서 여러 종목에 영향을 주는 위험을 알려주세요.",
  "현재 근거가 가장 부족한 Thesis는 무엇인가요?",
  "서로 충돌하는 가정을 가진 종목이 있나요?",
];

interface QueryResultEntry {
  id: string;
  question: string;
  response: PortfolioQueryResponse;
  askedAt: string;
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString("ko-KR");
}

function EvidenceCard({ evidence }: { evidence: PortfolioQueryEvidence }) {
  return (
    <article className="qa-evidence-card">
      <div className="evidence-meta">
        <span>{evidence.ticker}</span>
        <span>{evidence.classification} · {evidence.impact}</span>
        {evidence.published_at ? (
          <time dateTime={evidence.published_at}>{formatDateTime(evidence.published_at)}</time>
        ) : (
          <span className="evidence-date">날짜 정보 없음</span>
        )}
      </div>
      <p>{evidence.content_snippet}</p>
      {evidence.related_assumptions.length > 0 && (
        <p className="qa-evidence-assumptions">{evidence.related_assumptions.join(" · ")}</p>
      )}
      {evidence.source_url && (
        <a href={evidence.source_url} rel="noreferrer" target="_blank">원문 보기 ↗</a>
      )}
    </article>
  );
}

function ResultCard({ entry }: { entry: QueryResultEntry }) {
  const { response } = entry;
  const [copied, setCopied] = useState(false);

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(response.answer);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <article className="qa-result">
      <div className="panel qa-answer-block">
        <p className="qa-question">{entry.question}</p>
        <div className="qa-answer">
          <p>{response.answer}</p>
        </div>
        <div className="qa-answer-meta">
          <time dateTime={entry.askedAt}>{formatDateTime(entry.askedAt)}</time>
          <button onClick={() => { void copyAnswer(); }} type="button">
            {copied ? "복사됨" : "답변 복사"}
          </button>
        </div>
        <p className="qa-disclaimer">이 답변은 투자 조언이 아니며 참고용 의사결정 지원 정보입니다.</p>

        {response.limitations.length > 0 && (
          <div className="qa-limitations">
            <strong>답변의 한계</strong>
            <ul>
              {response.limitations.map((limitation, index) => (
                <li key={index}>{limitation}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="qa-evidence-column">
        {response.evidence.length > 0 ? (
          <div className="qa-evidence-list">
            {response.evidence.map((evidence) => (
              <EvidenceCard evidence={evidence} key={evidence.document_id} />
            ))}
          </div>
        ) : (
          <div className="history-empty qa-evidence-empty">
            <strong>이 답변에는 직접 연결된 근거 문서가 없습니다.</strong>
            <p>답변의 한계를 확인해 주세요.</p>
          </div>
        )}
      </div>
    </article>
  );
}

export function PortfolioQueryPanel({
  holdingCount,
  mode,
  portfolioId,
  thesisCount,
}: {
  holdingCount: number;
  mode: ApiMode;
  portfolioId: string;
  thesisCount: number;
}) {
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<QueryResultEntry[]>([]);
  const textareaId = useId();

  const trimmedLength = question.trim().length;
  const canSubmit = trimmedLength > 0 && trimmedLength <= MAX_QUESTION_LENGTH && !submitting;

  const submitQuestion = async (rawQuestion: string) => {
    const trimmed = rawQuestion.trim();
    if (!trimmed || trimmed.length > MAX_QUESTION_LENGTH || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await queryPortfolio(portfolioId, trimmed, mode);
      setResults((current) => [
        { id: crypto.randomUUID(), question: trimmed, response, askedAt: new Date().toISOString() },
        ...current,
      ]);
      setQuestion("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "질문에 답변하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submitQuestion(question);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void submitQuestion(question);
    }
  };

  return (
    <section className="panel qa-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">06</span>
          <p className="kicker">PORTFOLIO Q&amp;A</p>
          <h2>포트폴리오에 물어보기</h2>
          <p>전체 포트폴리오 · Thesis {thesisCount}개 (보유 {holdingCount}종목) · 최근 근거 최대 50개</p>
        </div>
      </div>

      {results.length === 0 && (
        <div className="qa-suggestions">
          {SUGGESTED_QUESTIONS.map((suggestion) => (
            <button
              className="qa-suggestion-chip"
              disabled={submitting}
              key={suggestion}
              onClick={() => setQuestion(suggestion)}
              type="button"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <form className="qa-input-form" onSubmit={handleSubmit}>
        <label htmlFor={textareaId}>질문</label>
        <textarea
          disabled={submitting}
          id={textareaId}
          maxLength={MAX_QUESTION_LENGTH}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="예: 포트폴리오가 공통으로 의존하는 핵심 가정은 무엇인가요?"
          rows={3}
          value={question}
        />
        <div className="qa-input-footer">
          <span className="qa-char-count">{trimmedLength}/{MAX_QUESTION_LENGTH}자</span>
          <button className="primary-button" disabled={!canSubmit} type="submit">
            {submitting ? "확인하는 중…" : "질문하기"}
          </button>
        </div>
      </form>

      {submitting && (
        <p aria-live="polite" className="qa-loading">
          포트폴리오 Thesis와 근거를 검토하고 있습니다…
        </p>
      )}

      {error && (
        <div className="error-banner qa-error" role="alert">
          <span>{error}</span>
          <button onClick={() => { void submitQuestion(results[0]?.question ?? question); }} type="button">
            다시 시도
          </button>
        </div>
      )}

      {results.length === 0 && !submitting ? (
        <div className="history-empty">
          <strong>아직 질문한 내역이 없습니다.</strong>
          <p>위 추천 질문을 선택하거나 직접 입력해 보세요. 답변마다 사용한 근거와 한계를 함께 보여드립니다.</p>
        </div>
      ) : (
        <div className="qa-result-list" aria-live="polite">
          {results.map((entry) => (
            <ResultCard entry={entry} key={entry.id} />
          ))}
        </div>
      )}
    </section>
  );
}
