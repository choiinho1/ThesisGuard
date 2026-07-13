/**
 * ThesisGuard API client — single point of contact with the backend.
 *
 * Why this file exists: A(Frontend)는 B(Backend)가 실제 서버를 띄우지 않았거나
 * 엔드포인트/필드를 바꾸는 중이어도 화면 작업을 계속할 수 있어야 한다.
 * 그래서 모든 fetch 호출을 이 파일 하나로 모으고, mock/live 두 모드를 토글로
 * 전환할 수 있게 했다. index.html의 React 컴포넌트는 이 객체의 메서드만 호출하고,
 * 실제 백엔드 응답 형태는 backend/app/schemas.py 를 그대로 따른다 (필드명 1:1 매칭).
 *
 * B가 스키마를 바꾸면: 이 파일의 해당 함수 + 아래 MOCK 픽스처만 고치면 되고,
 * index.html의 컴포넌트 코드는 건드릴 필요가 없다 (그게 이 레이어를 분리한 이유).
 */
const ThesisGuardAPI = (function () {
  "use strict";

  const LIVE_BASE = window.THESISGUARD_API || "http://127.0.0.1:8000";
  const MODE_KEY = "thesisguard_mode"; // "live" | "mock"

  function getMode() {
    return localStorage.getItem(MODE_KEY) || "mock";
  }
  function setMode(mode) {
    localStorage.setItem(MODE_KEY, mode);
  }

  async function liveJson(path, options) {
    const resp = await fetch(`${LIVE_BASE}${path}`, options);
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /* ======================================================================
   * MOCK STORE — backend/app/models.py 의 필드명과 1:1로 맞췄다.
   * 새로고침하면 초기화된다 (의도적으로 영속화하지 않음 — 화면 작업용 fixture).
   * ==================================================================== */

  let nextId = 9000;
  const freshId = () => ++nextId;

  let mockPortfolios = [
    {
      id: 1,
      name: "AI Growth Portfolio",
      cash_ratio: 0.08,
      holdings: [
        { id: 101, ticker: "NVDA", quantity: 40, avg_price: 118.2, target_weight: 0.35, latest_confidence: 82, latest_status: "STRENGTHENED", has_thesis: true },
        { id: 102, ticker: "AVGO", quantity: 25, avg_price: 165.0, target_weight: 0.25, latest_confidence: 54, latest_status: "WEAKENED", has_thesis: true },
        { id: 103, ticker: "TSM", quantity: 60, avg_price: 142.5, target_weight: 0.20, latest_confidence: null, latest_status: null, has_thesis: false },
      ],
    },
  ];

  let mockTheses = {
    101: {
      id: 9101,
      holding_id: 101,
      raw_text: "NVIDIA는 AI 데이터센터 GPU 표준 지위를 바탕으로 성장할 것이다.",
      main_thesis: "NVIDIA는 AI 학습·추론 인프라의 사실상 표준 GPU 플랫폼 지위를 바탕으로 데이터센터向 매출 성장을 지속할 것이다.",
      key_premises: ["하이퍼스케일러의 AI 데이터센터 CAPEX가 지속 성장한다", "CUDA 생태계 종속성으로 전환 비용이 높다"],
      risks: ["Custom ASIC 확산으로 점유율 잠식 가능", "하이퍼스케일러 설비투자 축소 리스크"],
      versions: [
        { id: 1, confidence_score: 75, status: "UNCHANGED", timestamp: "2026-03-02T09:00:00Z", reason: { what_changed: "초기 등록" } },
        { id: 2, confidence_score: 82, status: "STRENGTHENED", timestamp: "2026-06-05T09:00:00Z", reason: { what_changed: "하이퍼스케일러 CAPEX 가이던스 상향" } },
      ],
      evidence: [
        { id: 1, source_id: "mock-news-1", source_text: "Meta Q1 2026 Earnings Call", related_premise: "하이퍼스케일러 CAPEX 성장", classification: "SUPPORT", impact: "HIGH", reasoning: "CAPEX 가이던스를 18% 상향 조정하며 AI 투자를 재확인했습니다.", created_at: "2026-06-05T09:00:00Z" },
      ],
    },
    102: {
      id: 9102,
      holding_id: 102,
      raw_text: "Broadcom은 Custom AI ASIC 수요로 성장할 것이다.",
      main_thesis: "Broadcom은 하이퍼스케일러向 Custom AI ASIC과 네트워킹 칩 수요 증가로 성장을 이어갈 것이다.",
      key_premises: ["주요 고객사의 Custom ASIC 물량이 지속 확대된다"],
      risks: ["소수 고객사 집중도가 높다"],
      versions: [
        { id: 1, confidence_score: 75, status: "UNCHANGED", timestamp: "2026-02-10T09:00:00Z", reason: { what_changed: "초기 등록" } },
        { id: 2, confidence_score: 54, status: "WEAKENED", timestamp: "2026-06-20T09:00:00Z", reason: { what_changed: "주요 고객사 물량 이연 가능성 보도" } },
      ],
      evidence: [
        { id: 1, source_id: "mock-news-2", source_text: "Broadcom Q2 2026 Earnings Call", related_premise: "Custom ASIC 물량 확대", classification: "CONTRADICT", impact: "HIGH", reasoning: "일부 고객 발주 시점이 다음 분기로 이연될 수 있다고 언급했습니다.", created_at: "2026-06-20T09:00:00Z" },
      ],
    },
  };

  // POST /api/theses/{id}/analyze 를 mock 모드에서 호출할 때마다 이 순서로 순환한다.
  // 실제 LangGraph 결과 다양성을 재현해서, 4가지 상태 전이에 대한 화면 반응을 전부 점검할 수 있게 한다.
  const ANALYZE_CYCLE = ["STRENGTHENED", "WEAKENED", "UNCHANGED", "BROKEN"];
  const ANALYZE_STEP = {};
  const SCENARIOS = {
    STRENGTHENED: { delta: 6, what_changed: "핵심 고객사의 신규 수주 공시로 수요 전제가 재확인되었습니다.", conflicting_premises: [], overall_judgment: "지지 근거가 추가되어 신뢰도가 상승했습니다.", watch_points: ["다음 분기 가이던스 반영 여부"], bull_argument: "신규 수주가 기존 수요 둔화 우려를 반박합니다.", bear_argument: "단일 수주라 반복성은 아직 검증되지 않았습니다.", classification: "SUPPORT", impact: "HIGH" },
    WEAKENED: { delta: -8, what_changed: "핵심 고객사가 설비투자 계획을 일부 축소한다고 발표했습니다.", conflicting_premises: ["하이퍼스케일러 CAPEX 성장 지속"], overall_judgment: "핵심 전제 중 하나가 흔들렸습니다.", watch_points: ["다음 실적 발표에서 가이던스 하향 여부"], bull_argument: "일시적 재고 조정일 가능성이 있습니다.", bear_argument: "구조적 수요 둔화의 초기 신호일 수 있습니다.", classification: "CONTRADICT", impact: "HIGH" },
    UNCHANGED: { delta: 0, what_changed: "이번 주기 동안 유의미한 신규 정보가 없었습니다.", conflicting_premises: [], overall_judgment: "기존 논리를 유지합니다.", watch_points: ["다음 실적 발표까지 모니터링"], bull_argument: "특별한 악재가 없다는 것 자체가 안정성을 보여줍니다.", bear_argument: "새로운 지지 근거도 없어 논리가 정체되고 있습니다.", classification: "NEUTRAL", impact: "LOW" },
    BROKEN: { delta: -25, what_changed: "핵심 고객사가 자체 설계 칩으로 전환한다고 공식 발표했습니다.", conflicting_premises: ["전환 비용 우위", "핵심 고객사향 매출 지속 성장"], overall_judgment: "핵심 전제가 정면으로 부정되었습니다. 논리 재검토가 필요합니다.", watch_points: ["전환 발표의 실제 물량·시점"], bull_argument: "발표와 실제 양산 사이 시차가 커 단기 영향은 제한적일 수 있습니다.", bear_argument: "핵심 전제가 무너진 사례로 다른 고객사로 확산될 위험이 있습니다.", classification: "CONTRADICT", impact: "HIGH" },
  };

  function findMockHolding(holdingId) {
    for (const p of mockPortfolios) {
      const h = p.holdings.find((x) => x.id === holdingId);
      if (h) return h;
    }
    return null;
  }

  // 빠른 추가는 "어느 포트폴리오에 넣을지" 고민 없이 티커+논리만 적으면 되도록,
  // 항상 첫 번째 포트폴리오(없으면 새로 "저장소"라는 이름으로 생성)에 담는다.
  // 실제 백엔드는 사용자별 기본 포트폴리오(예: "관심종목")를 두고 여기로 매핑하면 된다.
  function getOrCreateDefaultPortfolio() {
    if (mockPortfolios.length === 0) {
      mockPortfolios.push({ id: freshId(), name: "저장소", cash_ratio: 0, holdings: [] });
    }
    return mockPortfolios[0];
  }

  /* ============================== public API ============================= */

  async function listPortfolios() {
    if (getMode() === "mock") {
      await delay(150);
      return JSON.parse(JSON.stringify(mockPortfolios));
    }
    return liveJson("/api/portfolios");
  }

  async function getThesisByHolding(holdingId) {
    if (getMode() === "mock") {
      await delay(150);
      const thesis = mockTheses[holdingId];
      if (!thesis) {
        const err = new Error("No thesis registered for this holding yet");
        err.status = 404;
        throw err;
      }
      return JSON.parse(JSON.stringify(thesis));
    }
    const resp = await fetch(`${LIVE_BASE}/api/holdings/${holdingId}/thesis`);
    if (resp.status === 404) {
      const err = new Error("No thesis registered for this holding yet");
      err.status = 404;
      throw err;
    }
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  }

  async function createThesis(holdingId, rawText) {
    if (getMode() === "mock") {
      await delay(400); // LLM 호출 체감 지연 재현
      const thesis = {
        id: freshId(),
        holding_id: holdingId,
        raw_text: rawText,
        main_thesis: rawText.length > 90 ? rawText.slice(0, 90) + "…" : rawText,
        key_premises: ["mock 구조화 — 핵심 전제 예시 1", "mock 구조화 — 핵심 전제 예시 2"],
        risks: ["mock 구조화 — 리스크 예시 1"],
        versions: [{ id: 1, confidence_score: 75, status: "UNCHANGED", timestamp: new Date().toISOString(), reason: { what_changed: "초기 등록" } }],
        evidence: [],
      };
      mockTheses[holdingId] = thesis;
      const holding = findMockHolding(holdingId);
      if (holding) {
        holding.has_thesis = true;
        holding.latest_confidence = 75;
        holding.latest_status = "UNCHANGED";
      }
      return JSON.parse(JSON.stringify(thesis));
    }
    return liveJson(`/api/holdings/${holdingId}/thesis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText }),
    });
  }

  async function analyzeThesis(thesisId) {
    if (getMode() === "mock") {
      await delay(600); // 5회 LLM 호출 파이프라인 체감 지연 재현
      const thesis = Object.values(mockTheses).find((t) => t.id === thesisId);
      if (!thesis) throw new Error("Thesis not found");
      const holding = findMockHolding(thesis.holding_id);
      const latest = thesis.versions[thesis.versions.length - 1];
      const previousConfidence = latest ? latest.confidence_score : 75;
      const previousStatus = latest ? latest.status : "UNCHANGED";

      const step = ANALYZE_STEP[thesisId] || 0;
      const key = ANALYZE_CYCLE[step % ANALYZE_CYCLE.length];
      ANALYZE_STEP[thesisId] = step + 1;
      const sc = SCENARIOS[key];
      const newConfidence = Math.max(0, Math.min(100, previousConfidence + sc.delta));

      thesis.versions.push({ id: thesis.versions.length + 1, confidence_score: newConfidence, status: key, timestamp: new Date().toISOString(), reason: { what_changed: sc.what_changed } });
      const evRow = { id: (thesis.evidence.length || 0) + 1, source_id: `mock-news-${Date.now()}`, source_text: "mock 뉴스 배치 (node_research.py 목데이터 대응)", related_premise: thesis.key_premises[0] || null, classification: sc.classification, impact: sc.impact, reasoning: sc.what_changed, created_at: new Date().toISOString() };
      thesis.evidence.push(evRow);

      if (holding) {
        holding.latest_confidence = newConfidence;
        holding.latest_status = key;
      }

      return {
        ticker: holding ? holding.ticker : "",
        previous_confidence: previousConfidence,
        new_confidence: newConfidence,
        previous_status: previousStatus,
        new_status: key,
        what_changed: sc.what_changed,
        conflicting_premises: sc.conflicting_premises,
        overall_judgment: sc.overall_judgment,
        watch_points: sc.watch_points,
        bull_argument: sc.bull_argument,
        bear_argument: sc.bear_argument,
        evidence: [evRow],
      };
    }
    return liveJson(`/api/theses/${thesisId}/analyze`, { method: "POST" });
  }

  // 티커 + 투자 논리를 한 번에 등록한다 (포트폴리오를 먼저 고르거나 만들 필요 없음).
  // live 모드에서는 백엔드에 POST /api/holdings/quick-add (body: {ticker, raw_text})
  // 엔드포인트를 추가해야 한다. 응답은 holdings 배열의 항목 하나와 동일한 형태
  // ({id, ticker, quantity, avg_price, target_weight, latest_confidence, latest_status, has_thesis})
  // 이면 되고, 서버 쪽에서 사용자의 기본 포트폴리오(예: "관심종목")에 담아주면 된다.
  async function quickAddHolding(ticker, rawText) {
    if (getMode() === "mock") {
      await delay(200);
      const portfolio = getOrCreateDefaultPortfolio();
      const holdingId = freshId();
      const holding = {
        id: holdingId,
        ticker: ticker.toUpperCase(),
        quantity: 0,
        avg_price: 0,
        target_weight: 0,
        latest_confidence: null,
        latest_status: null,
        has_thesis: false,
      };
      portfolio.holdings.unshift(holding);
      await createThesis(holdingId, rawText); // has_thesis/confidence/status를 갱신해준다
      return JSON.parse(JSON.stringify(holding));
    }
    return liveJson("/api/holdings/quick-add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: ticker.toUpperCase(), raw_text: rawText }),
    });
  }

  return {
    LIVE_BASE,
    getMode,
    setMode,
    listPortfolios,
    getThesisByHolding,
    createThesis,
    analyzeThesis,
    quickAddHolding,
  };
})();
