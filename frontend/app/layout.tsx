import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ThesisGuard — Portfolio Intelligence",
  description: "투자 논리를 근거 기반으로 지속 검증하는 포트폴리오 대시보드",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
