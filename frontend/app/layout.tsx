import type { Metadata } from "next";
import "./globals.css";
import { MarketIndexTicker } from "@/components/MarketIndexTicker";
import { FeedbackButton } from "@/components/FeedbackButton";

export const metadata: Metadata = {
  title: "ThesisGuard | 투자 논리 관리",
  description: "투자 논리를 근거 기반으로 지속적으로 검증하는 포트폴리오 의사결정 도구",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <MarketIndexTicker />
        {children}
        <FeedbackButton />
      </body>
    </html>
  );
}
