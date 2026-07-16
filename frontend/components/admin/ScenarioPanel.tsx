"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createEvalScenario,
  deleteEvalScenario,
  listEvalScenarios,
  runEvalScenario,
} from "@/lib/apiClient";
import type { EvalRun, EvalScenario } from "@/types/schema";

export function ScenarioPanel() {
  const [scenarios, setScenarios] = useState<EvalScenario[]>([]);
  const [results, setResults] = useState<Record<string, EvalRun>>({});
  const [runningId, setRunningId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");

  const refresh = useCallback(async () => {
    await Promise.resolve();
    setLoading(true);
    setError(null);
    try {
      setScenarios(await listEvalScenarios());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "시나리오를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // One-time fetch on mount, no reactive dependency to sync against.
    /* eslint-disable react-hooks/set-state-in-effect */
    void refresh();
    /* eslint-enable react-hooks/set-state-in-effect */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !question.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const scenario = await createEvalScenario({
        name: name.trim(),
        category: "portfolio_qa",
        question: question.trim(),
        context_snapshot: {},
        expected_document_ids: [],
        required_keywords: [],
        forbidden_terms: [],
        is_active: true,
      });
      setScenarios((prev) => [scenario, ...prev]);
      setName("");
      setQuestion("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "시나리오를 추가하지 못했습니다.");
    } finally {
      setCreating(false);
    }
  }

  async function handleRun(scenarioId: string) {
    setRunningId(scenarioId);
    setError(null);
    try {
      const run = await runEvalScenario(scenarioId);
      setResults((prev) => ({ ...prev, [scenarioId]: run }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "시나리오 실행에 실패했습니다.");
    } finally {
      setRunningId(null);
    }
  }

  async function handleDelete(scenarioId: string) {
    try {
      await deleteEvalScenario(scenarioId);
      setScenarios((prev) => prev.filter((item) => item.id !== scenarioId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "시나리오를 삭제하지 못했습니다.");
    }
  }

  return (
    <div className="admin-panel-stack">
      {error && <div className="admin-error">{error}</div>}

      <section className="panel">
        <div className="panel-heading compact">
          <h2>시나리오 추가</h2>
        </div>
        <p className="admin-panel-intro">
          설정 값을 바꾼 뒤 이 시나리오들을 실행해 답변 품질이 유지되는지 바로 확인할 수 있습니다.
        </p>
        <form className="admin-scenario-form" onSubmit={(event) => void handleCreate(event)}>
          <label>
            <span>시나리오 이름</span>
            <input onChange={(event) => setName(event.target.value)} value={name} />
          </label>
          <label>
            <span>질문</span>
            <input onChange={(event) => setQuestion(event.target.value)} value={question} />
          </label>
          <button className="primary-button" disabled={creating} type="submit">
            {creating ? "추가 중..." : "추가"}
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="panel-heading compact">
          <h2>등록된 시나리오 ({scenarios.length}건)</h2>
        </div>
        {loading && <p className="admin-panel-note">불러오는 중...</p>}
        <div className="admin-scenario-list">
          {scenarios.map((scenario) => {
            const result = results[scenario.id];
            return (
              <article className="admin-scenario-card" key={scenario.id}>
                <header>
                  <strong>{scenario.name}</strong>
                  <span>{scenario.category}</span>
                </header>
                <p>{scenario.question}</p>
                <div className="admin-scenario-actions">
                  <button
                    className="primary-button"
                    disabled={runningId === scenario.id}
                    onClick={() => void handleRun(scenario.id)}
                    type="button"
                  >
                    {runningId === scenario.id ? "실행 중..." : "실행"}
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => void handleDelete(scenario.id)}
                    type="button"
                  >
                    삭제
                  </button>
                </div>
                {result && (
                  <div className="admin-scenario-result">
                    <span className={result.status === "FAILED" ? "is-negative" : "is-positive"}>
                      {result.status}
                    </span>
                    {result.status === "SUCCEEDED" ? (
                      <pre>{JSON.stringify(result.metrics, null, 2)}</pre>
                    ) : (
                      <p>{result.error_message}</p>
                    )}
                  </div>
                )}
              </article>
            );
          })}
          {!loading && scenarios.length === 0 && (
            <p className="admin-panel-note">등록된 시나리오가 없습니다.</p>
          )}
        </div>
      </section>
    </div>
  );
}
