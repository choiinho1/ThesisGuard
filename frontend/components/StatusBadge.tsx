import type { ThesisStatus } from "@/types/schema";

const labels: Record<ThesisStatus, string> = {
  STRONGLY_STRENGTHENED: "크게 강화",
  STRENGTHENED: "강화",
  UNCHANGED: "유지",
  WEAKENED: "약화",
  STRONGLY_WEAKENED: "크게 약화",
  BROKEN: "논리 붕괴",
};

export function StatusBadge({ status }: { status: ThesisStatus }) {
  return <span className={`status status--${status.toLowerCase()}`}>{labels[status]}</span>;
}
