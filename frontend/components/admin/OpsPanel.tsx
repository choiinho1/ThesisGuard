"use client";

import { useCallback, useEffect, useState } from "react";
import { getAdminHealth, listAdminSchedules, listLangfuseTraces } from "@/lib/apiClient";
import type { AdminHealth, AdminScheduleOverview, LangfuseTrace } from "@/types/schema";

function formatDateTime(value: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR");
}

function formatLatency(value: number | null) {
  if (value === null) return "-";
  return `${value.toFixed(2)}초`;
}

function formatCost(value: number | null) {
  if (value === null) return "-";
  return `$${value.toFixed(4)}`;
}

export function OpsPanel() {
  const [schedules, setSchedules] = useState<AdminScheduleOverview[]>([]);
  const [health, setHealth] = useState<AdminHealth | null>(null);
  const [traces, setTraces] = useState<LangfuseTrace[]>([]);
  const [tracesError, setTracesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    await Promise.resolve();
    setLoading(true);
    setError(null);
    try {
      const [scheduleRows, healthStatus] = await Promise.all([
        listAdminSchedules(),
        getAdminHealth(),
      ]);
      setSchedules(scheduleRows);
      setHealth(healthStatus);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "운영 현황을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }

    setTracesError(null);
    try {
      setTraces(await listLangfuseTraces());
    } catch (caught) {
      setTracesError(
        caught instanceof Error ? caught.message : "Langfuse 트레이스를 불러오지 못했습니다.",
      );
    }
  }, []);

  useEffect(() => {
    // One-time fetch on mount, no reactive dependency to sync against.
    /* eslint-disable react-hooks/set-state-in-effect */
    void refresh();
    /* eslint-enable react-hooks/set-state-in-effect */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) return <div className="panel">운영 현황을 불러오는 중...</div>;

  return (
    <div className="admin-panel-stack">
      {error && <div className="admin-error">{error}</div>}

      {health && (
        <section className="panel">
          <div className="panel-heading compact">
            <h2>시스템 상태</h2>
          </div>
          <div className="admin-health-grid">
            <div><span>DB</span><strong>{health.database}</strong></div>
            <div><span>LLM Provider</span><strong>{health.llm_provider}</strong></div>
            <div><span>RAG</span><strong>{health.rag_enabled ? "활성" : "비활성"}</strong></div>
            <div><span>Langfuse</span><strong>{health.langfuse}</strong></div>
            <div><span>스케줄러</span><strong>{health.scheduler_enabled ? "실행 중" : "중지"}</strong></div>
            <div><span>폴링 주기</span><strong>{health.scheduler_poll_seconds}초</strong></div>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading compact">
          <h2>예약 재분석 현황 ({schedules.length}건)</h2>
        </div>
        <div className="admin-table">
          <div className="admin-table-row admin-table-head">
            <span>종목</span>
            <span>사용자</span>
            <span>다음 실행</span>
            <span>마지막 실행</span>
            <span>최근 상태</span>
          </div>
          {schedules.map((schedule) => (
            <div className="admin-table-row" key={schedule.schedule_id}>
              <span>{schedule.ticker}</span>
              <span>{schedule.user_email}</span>
              <span>{formatDateTime(schedule.next_run_at)}</span>
              <span>{formatDateTime(schedule.last_run_at)}</span>
              <span className={schedule.latest_run_status === "FAILED" ? "is-negative" : ""}>
                {schedule.latest_run_status ?? "-"}
                {schedule.latest_run_error && (
                  <small title={schedule.latest_run_error}> ⚠</small>
                )}
              </span>
            </div>
          ))}
          {schedules.length === 0 && <p className="admin-panel-note">등록된 예약이 없습니다.</p>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading compact">
          <h2>Langfuse 최근 트레이스 ({traces.length}건)</h2>
          {health && (
            <a
              className="secondary-button"
              href={health.langfuse_base_url}
              rel="noreferrer"
              target="_blank"
            >
              Langfuse에서 열기
            </a>
          )}
        </div>
        {tracesError && <div className="admin-error">{tracesError}</div>}
        <p className="admin-panel-note">
          최근 트레이스 요약만 표시합니다. 스팬 트리·프롬프트 등 상세 정보는 Langfuse에서 확인하세요.
        </p>
        <div className="admin-table">
          <div className="admin-table-row admin-table-head">
            <span>이름</span>
            <span>사용자</span>
            <span>시각</span>
            <span>지연시간</span>
            <span>비용</span>
          </div>
          {traces.map((trace) => (
            <div className="admin-table-row" key={trace.id}>
              <span>{trace.name ?? "-"}</span>
              <span>{trace.user_id ?? "-"}</span>
              <span>{formatDateTime(trace.timestamp)}</span>
              <span>{formatLatency(trace.latency_seconds)}</span>
              <span>{formatCost(trace.total_cost)}</span>
            </div>
          ))}
          {traces.length === 0 && !tracesError && (
            <p className="admin-panel-note">표시할 트레이스가 없습니다.</p>
          )}
        </div>
      </section>
    </div>
  );
}
