"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { listAdminSettings, updateAdminSetting } from "@/lib/apiClient";
import type { AppSetting } from "@/types/schema";

const CATEGORY_LABELS: Record<string, string> = {
  scoring: "스코어링 가중치",
  policy: "알림 정책",
  scheduler: "예약 재분석",
  llm: "LLM",
  rag: "RAG 검색",
  qa: "포트폴리오 Q&A",
};

// Fixed display order, independent of whatever order the API/mock data
// happens to arrive in (mock is hand-written insertion order; the live API
// returns rows ordered alphabetically by category — the two disagreed
// before this list existed, so settings appeared in a different order
// depending on mode).
const CATEGORY_ORDER = ["scoring", "policy", "scheduler", "llm", "rag", "qa"];

function parseInputValue(raw: string, previous: AppSetting["value"]): AppSetting["value"] {
  if (typeof previous === "boolean") return raw === "true";
  if (typeof previous === "number") {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : previous;
  }
  return raw;
}

export function SettingsPanel() {
  const [settings, setSettings] = useState<AppSetting[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    await Promise.resolve();
    setLoading(true);
    setError(null);
    try {
      const rows = await listAdminSettings();
      setSettings(rows);
      setDrafts(Object.fromEntries(rows.map((row) => [row.key, String(row.value)])));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "설정을 불러오지 못했습니다.");
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

  const grouped = useMemo(() => {
    const groups = new Map<string, AppSetting[]>();
    for (const setting of settings) {
      const bucket = groups.get(setting.category) ?? [];
      bucket.push(setting);
      groups.set(setting.category, bucket);
    }
    for (const bucket of groups.values()) {
      bucket.sort((a, b) => a.key.localeCompare(b.key));
    }
    const orderIndex = (category: string) => {
      const index = CATEGORY_ORDER.indexOf(category);
      return index === -1 ? CATEGORY_ORDER.length : index;
    };
    return Array.from(groups.entries()).sort(
      ([a], [b]) => orderIndex(a) - orderIndex(b),
    );
  }, [settings]);

  async function saveSetting(setting: AppSetting) {
    setSavingKey(setting.key);
    setError(null);
    try {
      const value = parseInputValue(drafts[setting.key] ?? "", setting.value);
      const updated = await updateAdminSetting(setting.key, value);
      setSettings((prev) => prev.map((row) => (row.key === updated.key ? updated : row)));
      setSavedKey(setting.key);
      setTimeout(() => setSavedKey((current) => (current === setting.key ? null : current)), 1800);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "설정을 저장하지 못했습니다.");
    } finally {
      setSavingKey(null);
    }
  }

  if (loading) return <div className="panel">설정을 불러오는 중...</div>;

  return (
    <div className="admin-panel-stack">
      <p className="admin-panel-intro">
        값을 바꾸고 저장하면 재배포 없이 다음 분석 실행부터 바로 반영됩니다.
      </p>
      {error && <div className="admin-error">{error}</div>}
      {grouped.map(([category, rows]) => (
        <section className="panel admin-settings-group" key={category}>
          <div className="panel-heading compact">
            <h2>{CATEGORY_LABELS[category] ?? category}</h2>
          </div>
          <div className="admin-settings-list">
            {rows.map((setting) => (
              <div className="admin-settings-row" key={setting.key}>
                <div className="admin-settings-label">
                  <code>{setting.key}</code>
                  <span>{setting.description}</span>
                </div>
                <input
                  onChange={(event) =>
                    setDrafts((prev) => ({ ...prev, [setting.key]: event.target.value }))
                  }
                  value={drafts[setting.key] ?? ""}
                />
                <button
                  className="primary-button"
                  disabled={savingKey === setting.key}
                  onClick={() => void saveSetting(setting)}
                  type="button"
                >
                  {savingKey === setting.key ? "저장 중..." : savedKey === setting.key ? "저장됨" : "저장"}
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
