"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminConsole } from "@/components/admin/AdminConsole";
import { getApiMode } from "@/lib/apiClient";
import { getCurrentUser, hasAccessToken } from "@/lib/authClient";
import type { AuthUser } from "@/types/schema";

type GateStatus = "checking" | "unauthenticated" | "denied" | "ok";

const DEMO_ADMIN_USER: AuthUser = {
  id: "demo-user",
  email: "demo@thesisguard.local",
  name: "Demo",
  role: "admin",
  created_at: new Date(0).toISOString(),
};

export function AdminGate() {
  const [status, setStatus] = useState<GateStatus>("checking");
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const restoreSession = async () => {
      const demoBypassEnabled =
        process.env.NEXT_PUBLIC_DEMO_BYPASS_AUTH === "true" || getApiMode() !== "live";
      if (demoBypassEnabled) {
        setUser(DEMO_ADMIN_USER);
        setStatus("ok");
        return;
      }

      if (!hasAccessToken()) {
        setStatus("unauthenticated");
        return;
      }

      try {
        const current = await getCurrentUser();
        setUser(current);
        setStatus(current.role === "admin" ? "ok" : "denied");
      } catch {
        setStatus("unauthenticated");
      }
    };

    void restoreSession();
  }, []);

  if (status === "checking") return <main className="loading-screen">관리자 권한을 확인하는 중...</main>;

  if (status === "unauthenticated") {
    return (
      <main className="admin-denied">
        <h1>로그인이 필요합니다</h1>
        <p>관리자 콘솔은 로그인 후 이용할 수 있습니다.</p>
        <Link href="/">메인으로 이동</Link>
      </main>
    );
  }

  if (status === "denied") {
    return (
      <main className="admin-denied">
        <h1>관리자 권한이 필요합니다</h1>
        <p>{user?.email} 계정은 관리자 콘솔에 접근할 수 없습니다.</p>
        <Link href="/">메인으로 이동</Link>
      </main>
    );
  }

  return <AdminConsole />;
}
