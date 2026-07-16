"use client";

import { useEffect, useState } from "react";
import { getApiMode, getMarketTicker } from "@/lib/apiClient";
import type { TickerQuote } from "@/types/schema";

type IndexInstrument = {
  symbol: string;
  price: number;
  changePct: number;
  decimals: number;
};

// live 모드에서 백엔드가 돌려주는 심볼(야후 파이낸스 티커 기준)을 화면 표시용
// 라벨로 바꾼다. mock 모드의 INITIAL_INSTRUMENTS와 라벨을 맞춰야 모드 전환 시
// 같은 항목끼리 자연스럽게 값만 갱신된다.
const LIVE_SYMBOL_LABELS: Record<string, string> = {
  "코스피": "코스피",
  VIX: "VIX",
  TNX: "美 10Y",
  "BTC-USD": "BTC-USD",
  "ETH-USD": "ETH-USD",
  GSPC: "S&P500",
  "나스닥": "나스닥",
  "USD/KRW": "USD/KRW",
};

// mock 모드에서는 미세 변동을 시뮬레이션하고, live 모드에서는 실제 값이 올
// 때까지의 초기 화면(및 개별 항목 조회 실패 시 폴백)으로 쓰인다.
const INITIAL_INSTRUMENTS: IndexInstrument[] = [
  { symbol: "코스피", price: 2992.54, changePct: 1.22, decimals: 2 },
  { symbol: "VIX", price: 15.84, changePct: -6.27, decimals: 2 },
  { symbol: "美 10Y", price: 4.54, changePct: -0.66, decimals: 2 },
  { symbol: "BTC-USD", price: 63885.53, changePct: 1.49, decimals: 2 },
  { symbol: "ETH-USD", price: 1773.71, changePct: 1.26, decimals: 2 },
  { symbol: "S&P500", price: 5487.03, changePct: 0.31, decimals: 2 },
  { symbol: "나스닥", price: 17862.4, changePct: 0.58, decimals: 2 },
  { symbol: "USD/KRW", price: 1372.1, changePct: -0.14, decimals: 2 },
];

const MOCK_TICK_MS = 2000;
// 매 폴링마다 실제로 야후 파이낸스에 8건씩 요청(캐시 없음)하므로 mock의
// 2초 주기보다 훨씬 느슨하게 잡는다.
const LIVE_POLL_MS = 30000;

function mergeLiveQuotes(prev: IndexInstrument[], quotes: TickerQuote[]): IndexInstrument[] {
  return quotes.map((quote) => {
    const symbol = LIVE_SYMBOL_LABELS[quote.symbol] ?? quote.symbol;
    const fallback = prev.find((inst) => inst.symbol === symbol);
    return {
      symbol,
      price: quote.price ?? fallback?.price ?? 0,
      changePct: quote.change_pct ?? fallback?.changePct ?? 0,
      decimals: fallback?.decimals ?? 2,
    };
  });
}

function formatPrice(value: number, decimals: number) {
  return value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function changeClass(changePct: number) {
  if (changePct > 0) return "is-positive";
  if (changePct < 0) return "is-negative";
  return "is-flat";
}

export function MarketIndexTicker() {
  const [instruments, setInstruments] = useState(INITIAL_INSTRUMENTS);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      const mode = getApiMode();
      if (mode === "live") {
        try {
          const quotes = await getMarketTicker("live");
          if (!cancelled) setInstruments((prev) => mergeLiveQuotes(prev, quotes));
        } catch {
          // 조회 실패 시 마지막으로 받은 값을 그대로 유지한다.
        }
      } else {
        setInstruments((prev) =>
          prev.map((inst) => ({
            ...inst,
            price: Math.max(0, inst.price + (Math.random() - 0.5) * (inst.price * 0.0025)),
            changePct: inst.changePct + (Math.random() - 0.5) * 0.15,
          })),
        );
      }
      if (!cancelled) {
        // 다음 주기는 이번 tick이 끝난 뒤의 최신 모드를 기준으로 정한다 —
        // mock<->live 전환이 즉시 폴링 주기에 반영되도록.
        timer = setTimeout(tick, getApiMode() === "live" ? LIVE_POLL_MS : MOCK_TICK_MS);
      }
    }

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const track = [...instruments, ...instruments];

  return (
    <div className="market-ticker-wrap" aria-label="실시간 시장 지표">
      <div className="market-ticker-track">
        {track.map((inst, i) => (
          <div className="market-ticker-item" key={`${inst.symbol}-${i}`}>
            <span className="market-ticker-symbol">{inst.symbol}</span>
            <span className="market-ticker-price">{formatPrice(inst.price, inst.decimals)}</span>
            <span className={`market-ticker-change ${changeClass(inst.changePct)}`}>
              {inst.changePct > 0 ? "▲" : inst.changePct < 0 ? "▼" : "•"} {Math.abs(inst.changePct).toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
