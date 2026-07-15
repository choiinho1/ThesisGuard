"use client";

import { useEffect, useState } from "react";
import {
  deleteAnalysisSchedule,
  listAnalysisSchedules,
  saveAnalysisSchedule,
} from "@/lib/apiClient";
import type { AnalysisSchedule, ApiMode, DashboardHolding } from "@/types/schema";

const DEFAULT_TIME = "09:00";
const SEOUL_TIMEZONE = "Asia/Seoul";

function compactTime(value: string) {
  return value.slice(0, 5);
}

function formatDate(value: string | null) {
  if (!value) return "아직 실행되지 않음";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: SEOUL_TIMEZONE,
  }).format(new Date(value));
}

export function AutoAnalysisSchedule({
  holding,
  mode,
}: {
  holding: DashboardHolding;
  mode: ApiMode;
}) {
  const [schedule, setSchedule] = useState<AnalysisSchedule | null>(null);
  const [dailyTime, setDailyTime] = useState(DEFAULT_TIME);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void listAnalysisSchedules(mode)
      .then((items) => {
        if (cancelled) return;
        const current = items.find((item) => item.holding_id === holding.id) ?? null;
        setSchedule(current);
        setDailyTime(current ? compactTime(current.daily_time) : DEFAULT_TIME);
        setEnabled(current?.enabled ?? true);
      })
      .catch((error: unknown) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "예약을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [holding.id, mode]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const saved = await saveAnalysisSchedule(holding.id, {
        enabled,
        daily_time: dailyTime,
        timezone: SEOUL_TIMEZONE,
      }, mode);
      setSchedule({ ...saved, ticker: holding.ticker });
      setMessage(mode === "mock"
        ? "목 모드 미리보기입니다. Live 모드에서 저장하면 실제 자동 분석이 실행됩니다."
        : `${holding.ticker} 자동 분석 예약을 저장했습니다.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "예약을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await deleteAnalysisSchedule(holding.id, mode);
      setSchedule(null);
      setEnabled(true);
      setDailyTime(DEFAULT_TIME);
      setMessage("자동 분석 예약을 해제했습니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "예약을 해제하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="automation-strip" aria-labelledby={`automation-${holding.id}`}>
      <div className="automation-copy">
        <span className="automation-icon" aria-hidden="true">↻</span>
        <div>
          <div className="automation-title-row">
            <strong id={`automation-${holding.id}`}>{holding.ticker} 자동 재분석</strong>
            {schedule && (
              <span className={schedule.enabled ? "automation-state is-on" : "automation-state"}>
                {schedule.enabled ? "ON" : "PAUSED"}
              </span>
            )}
          </div>
          <p>매일 지정 시각에 새 근거를 분석하고, 점수가 변하면 이메일로 알려드립니다.</p>
          <small>MEDIUM·HIGH 근거는 History에 자동 보관됩니다.</small>
        </div>
      </div>

      <div className="automation-controls">
        <label>
          <span>실행 시각</span>
          <input
            aria-label={`${holding.ticker} 자동 분석 실행 시각`}
            disabled={loading || saving}
            onChange={(event) => setDailyTime(event.target.value)}
            type="time"
            value={dailyTime}
          />
        </label>
        <label className="automation-toggle">
          <input
            checked={enabled}
            disabled={loading || saving || !holding.thesis}
            onChange={(event) => setEnabled(event.target.checked)}
            type="checkbox"
          />
          <span>{enabled ? "자동 실행" : "일시 정지"}</span>
        </label>
        <button
          className="automation-save"
          disabled={loading || saving || (enabled && !holding.thesis)}
          onClick={save}
          type="button"
        >
          {saving ? "저장 중…" : schedule ? "변경 저장" : "예약 설정"}
        </button>
        {schedule && (
          <button className="automation-remove" disabled={saving} onClick={remove} type="button">
            해제
          </button>
        )}
      </div>

      {!holding.thesis && <p className="automation-notice">투자 논리를 먼저 등록하면 자동 분석을 켤 수 있습니다.</p>}
      {schedule && (
        <div className="automation-meta">
          <span>다음 실행 <strong>{formatDate(schedule.next_run_at)}</strong></span>
          <span>최근 실행 <strong>{formatDate(schedule.last_run_at)}</strong></span>
          <span>알림 <strong>{schedule.recipient_email}</strong></span>
        </div>
      )}
      {message && <p className="automation-message" role="status">{message}</p>}
    </section>
  );
}
