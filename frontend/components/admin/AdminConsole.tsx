"use client";

import Link from "next/link";
import { useState } from "react";
import { OpsPanel } from "@/components/admin/OpsPanel";
import { QaLogPanel } from "@/components/admin/QaLogPanel";
import { ScenarioPanel } from "@/components/admin/ScenarioPanel";
import { SettingsPanel } from "@/components/admin/SettingsPanel";

type AdminTab = "settings" | "ops" | "scenarios" | "qa-logs";

const TABS: { id: AdminTab; label: string }[] = [
  { id: "settings", label: "설정" },
  { id: "ops", label: "운영" },
  { id: "scenarios", label: "시나리오" },
  { id: "qa-logs", label: "Q&A 로그" },
];

export function AdminConsole() {
  const [tab, setTab] = useState<AdminTab>("settings");

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <p className="eyebrow">THESISGUARD ADMIN</p>
          <h1>관리자 콘솔</h1>
        </div>
        <Link className="secondary-button" href="/">
          대시보드로 돌아가기
        </Link>
      </header>

      <nav className="workspace-tabs" aria-label="관리자 콘솔 탭">
        {TABS.map((item) => (
          <button
            key={item.id}
            aria-current={tab === item.id ? "page" : undefined}
            className={tab === item.id ? "is-active" : ""}
            onClick={() => setTab(item.id)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="admin-content">
        {tab === "settings" && <SettingsPanel />}
        {tab === "ops" && <OpsPanel />}
        {tab === "scenarios" && <ScenarioPanel />}
        {tab === "qa-logs" && <QaLogPanel />}
      </div>
    </main>
  );
}
