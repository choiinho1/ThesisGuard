"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { listQaLogs } from "@/lib/apiClient";
import type { QaLogEntry } from "@/types/schema";

function downloadJsonl(logs: QaLogEntry[]) {
  const content = logs.map((log) => JSON.stringify(log)).join("\n");
  const blob = new Blob([content], { type: "application/jsonl" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `thesisguard-qa-logs-${new Date().toISOString().slice(0, 10)}.jsonl`;
  link.click();
  URL.revokeObjectURL(url);
}

export function QaLogPanel() {
  const [logs, setLogs] = useState<QaLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const refresh = useCallback(async () => {
    await Promise.resolve();
    setLoading(true);
    setError(null);
    try {
      setLogs(await listQaLogs());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Q&A 로그를 불러오지 못했습니다.");
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

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return logs;
    return logs.filter(
      (log) =>
        log.question.toLowerCase().includes(needle) ||
        log.answer.toLowerCase().includes(needle) ||
        log.user_email.toLowerCase().includes(needle),
    );
  }, [logs, filter]);

  if (loading) return <div className="panel">Q&A 로그를 불러오는 중...</div>;

  return (
    <div className="admin-panel-stack">
      {error && <div className="admin-error">{error}</div>}

      <section className="panel">
        <div className="panel-heading">
          <h2>Q&A 로그 ({filtered.length}건)</h2>
          <button
            className="secondary-button"
            disabled={filtered.length === 0}
            onClick={() => downloadJsonl(filtered)}
            type="button"
          >
            JSONL로 내보내기
          </button>
        </div>
        <p className="admin-panel-intro">
          사용자가 포트폴리오에 질문하고 받은 답변을 모두 기록합니다. 향후 학습 데이터로 활용할 수 있습니다.
        </p>
        <input
          className="admin-qa-filter"
          onChange={(event) => setFilter(event.target.value)}
          placeholder="질문/답변/이메일 검색"
          value={filter}
        />
        <div className="admin-qa-list">
          {filtered.map((log) => (
            <article className="admin-qa-card" key={log.id}>
              <header>
                <span>{log.user_email}</span>
                <span>{new Date(log.created_at).toLocaleString("ko-KR")}</span>
              </header>
              <p className="admin-qa-question">Q. {log.question}</p>
              <p className="admin-qa-answer">A. {log.answer}</p>
              {log.evidence_document_ids.length > 0 && (
                <p className="admin-qa-evidence">
                  근거 {log.evidence_document_ids.length}건
                </p>
              )}
            </article>
          ))}
          {filtered.length === 0 && <p className="admin-panel-note">기록된 Q&A가 없습니다.</p>}
        </div>
      </section>
    </div>
  );
}
