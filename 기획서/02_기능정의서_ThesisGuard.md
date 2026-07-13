# 기능 정의서 — ThesisGuard

> PRD의 P0 기능(F-1~F-6)을 개발 가능한 수준으로 상세화했습니다. `ThesisGuard_Team_Guide.md`의 DB 스키마·API·LangGraph 설계를 근거로 작성했습니다.

## 문서 정보

| 항목 | 내용 |
|---|---|
| 상태 | Draft · v0.1 |
| 작성자 | ThesisGuard 팀 (A·B·C 공동) |
| 관련 문서 | PRD · TDD · ADR |

## 1. 범위 & 용어

**범위**: 웹 서비스(Next.js 대시보드). 관리자 화면·모바일 네이티브는 1차 범위 외.

**용어**:
- **Thesis(투자 논리)**: 사용자가 특정 종목을 보유하는 근거를 구조화한 레코드 (`theses` 테이블).
- **Evidence(증거)**: Thesis와 대조되는 신규 정보 한 건 (`evidence` 테이블).
- **Classification**: 증거가 Thesis를 지지/반박하는지의 분류 (`SUPPORT`/`CONTRADICT`/`NEUTRAL`/`UNCERTAIN`).
- **Thesis Status**: 이번 분석으로 Thesis 전체가 어느 방향·강도로 바뀌었는지 (6단계).
- **Concentration(집중도)**: 포트폴리오 내 여러 종목이 의미적으로 공유하는 공통 전제(테마)의 비중.

## 2. 기능(FR) vs 비기능(NFR)

| 구분 | 정의 | 예시 |
|---|---|---|
| 기능(FR) | 시스템이 무엇을 하는가 | 신규 공시가 올라오면 기존 Thesis와 대조해 SUPPORT/CONTRADICT를 판정한다 |
| 비기능(NFR) | 얼마나 잘 하는가(품질·제약) | 모든 판정에는 근거 링크(source_url)가 반드시 포함된다 |

## 3. 기능 상세

### F-1 · 포트폴리오/보유종목 등록·관리 (P0)

| 항목 | 내용 |
|---|---|
| 기능 ID / 화면 ID | PORT-001 / SCR-PORTFOLIO |
| 사용자 스토리 | 투자자로서, 여러 포트폴리오를 만들고 종목·수량·평균매수가·목표비중을 관리하고 싶다 |
| 입력 | 포트폴리오명, 투자목적, 투자기간, 현금비중 / 종목별 ticker, 수량, 평균매수가, 목표비중 |
| 처리(주 흐름) | ① 포트폴리오 생성(`POST /api/portfolios`) → ② 종목 추가(`POST /api/portfolios/{id}/holdings`) → ③ 리밸런싱 시 변경 전/후 스냅샷을 `transactions`에 기록(`POST /api/portfolios/{id}/rebalance`) |
| 출력 | 포트폴리오 목록, 종목별 현재 비중(current_weight), 리밸런싱 히스토리 타임라인 |
| 예외 | 존재하지 않는 ticker 입력 → 검증 실패 안내 / 목표비중 합계가 100% 초과 → 경고 / 종목 삭제 시 연결된 Thesis 존재 → 함께 삭제할지 확인 |
| 상태 | 없음 → 등록됨 → 보유중 → 청산됨 |
| 인수 기준 | Given 유효한 종목 정보를, When 등록하면, Then holdings 테이블에 저장되고 대시보드에 즉시 반영된다 |

### F-2 · 투자 논리 자연어 입력 → 자동 구조화 (P0)

| 항목 | 내용 |
|---|---|
| 기능 ID / 화면 ID | THESIS-001 / SCR-THESIS-INPUT |
| 사용자 스토리 | 투자자로서, 매수 이유를 자유롭게 적으면 AI가 핵심 전제·신호·리스크로 정리해주길 원한다 |
| 입력 | 자연어 원문(raw_input, 자유 서술) |
| 처리(주 흐름) | ① `POST /api/holdings/{id}/thesis`로 원문 등록 → ② C가 Main Thesis / 핵심 전제(key_assumptions) / 긍정 신호(positive_signals) / 부정 신호(negative_signals) / 주요 리스크(key_risks)로 구조화 → ③ 초기 confidence_score·status 산정 → ④ `theses` 테이블 저장 |
| 출력 | 구조화된 Thesis 카드(Main Thesis, 핵심 전제 목록, 긍정/부정 신호, 리스크) + 사용자 수정 가능한 폼 |
| 예외 | 원문이 너무 짧아 구조화 근거 부족 → 추가 입력 요청 / 이미 Thesis가 존재하는 종목에 재등록 → 새 버전(`thesis_versions`)으로 처리할지 확인 |
| 상태 | 미등록 → 구조화중 → 등록완료 |
| 인수 기준 | Given 자연어 투자 논리를, When 등록하면, Then Main Thesis·핵심 전제·긍정/부정 신호·리스크가 각각 채워져 표시된다 |

### F-3 · 신규 정보 수집 및 Thesis 대조 분석 (P0) — *Thesis Change Detection*

| 항목 | 내용 |
|---|---|
| 기능 ID / 화면 ID | ANALYZE-001 / SCR-DASHBOARD |
| 사용자 스토리 | 투자자로서, 새로운 공시·뉴스·거시데이터가 내 논리에 어떤 영향을 주는지 알고 싶다 |
| 입력 | holding_id, portfolio_id (트리거: 사용자 요청 또는 주기적 실행) |
| 처리(주 흐름) | ① `POST /api/holdings/{id}/analyze` 호출 → ② B가 `run_analysis_workflow(portfolio_id, holding_id)` 실행 → ③ LangGraph: Filing/News/Macro Agent 병렬 수집(MCP Tool 경유) → ④ Evidence Extractor가 근거 단위로 분리 → ⑤ Thesis Analyzer가 기존 Thesis와 대조 → ⑥ 결과를 `ThesisAnalysisResult`로 반환 |
| 출력 | 신규 evidence 목록(분류·비중·근거 포함), 갱신된 Thesis 상태·Confidence |
| 예외 | 신규 정보가 없음 → `UNCHANGED` 처리 후 종료 / MCP Tool 응답 실패 → 해당 소스 제외하고 나머지로 진행(PRD 7절 실패 폴백) / 근거 불충분 → `UNCERTAIN` 처리 후 Additional Research 루프 1회 |
| 상태 | 대기 → 수집중 → 분석중 → 완료 \| 실패 |
| 인수 기준 | Given 기존 Thesis가 등록된 종목에서, When 분석을 실행하면, Then 신규 증거가 SUPPORT/CONTRADICT/NEUTRAL/UNCERTAIN로 분류되고 근거(reason)와 함께 표시된다 |

### F-4 · Thesis 변화 판정(6단계) 및 Confidence 산정 (P0)

| 항목 | 내용 |
|---|---|
| 기능 ID / 화면 ID | JUDGE-001 / SCR-DASHBOARD |
| 사용자 스토리 | 투자자로서, 이번 분석으로 내 논리가 얼마나 강화/약화됐는지 한눈에 알고 싶다 |
| 입력 | 분류된 evidence 목록, 기존 thesis_snapshot |
| 처리(주 흐름) | ① Bull Agent가 지지 근거로 강화 논거 생성 → ② Bear Agent가 반박 근거로 약화 논거 생성 → ③ Judge Agent가 둘을 종합해 `updated_confidence`(0~100)와 `updated_status`(6단계) 산정 → ④ `theses` 갱신 + `thesis_versions`에 새 버전 기록 |
| 출력 | STRONGLY_STRENGTHENED → STRENGTHENED → UNCHANGED → WEAKENED → STRONGLY_WEAKENED → BROKEN 중 하나 + Confidence 점수 + change_reason |
| 예외 | Bull/Bear 근거가 팽팽히 상충 → Judge가 `UNCHANGED`에 가깝게 보수적으로 판정하고 관찰 포인트(observation_points)에 기록 |
| 상태 | 분석중 → 판정완료 |
| 인수 기준 | Given Bull/Bear 리포트가 생성됐을 때, When Judge가 종합하면, Then thesis_versions에 새 버전이 기록되고 conflicting_assumptions가 명시된다 |

### F-5 · 설명형 Alert 및 이메일 발송 (P0) — *Explainable Alert*

| 항목 | 내용 |
|---|---|
| 기능 ID / 화면 ID | ALERT-001 / SCR-ALERTS |
| 사용자 스토리 | 투자자로서, 논리가 크게 흔들렸을 때 왜 흔들렸는지 설명과 함께 즉시 알림받고 싶다 |
| 입력 | alert_decision(`{"severity": ..., "should_send": ...}`), updated Thesis |
| 처리(주 흐름) | ① C가 thesis_status 변화 폭에 따라 severity(CRITICAL/MAJOR/MINOR/NONE) 산정 → ② B의 Alert Engine이 `alerts` 테이블에 저장 → ③ CRITICAL/MAJOR는 즉시 이메일 발송(SMTP), MINOR는 주간 요약에 모아서 발송 |
| 출력 | 알림 목록(제목, 본문 — 무엇이 변했는가/충돌한 전제/종합 판단/관찰 포인트), 이메일 |
| 예외 | 사용자가 알림 설정을 꺼둔 경우 → 발송하지 않고 목록에만 기록 / SMTP 발송 실패 → 재시도 큐에 적재 |
| 상태 | 생성됨 → 발송대기 → 발송완료 \| 발송실패 |
| 인수 기준 | Given severity가 CRITICAL일 때, When Alert가 생성되면, Then 즉시 이메일이 발송되고 본문에 변화 이유가 근거와 함께 포함된다 |

### F-6 · 포트폴리오 Thesis Concentration 분석 (P0) — *Thesis Concentration Analysis*

| 항목 | 내용 |
|---|---|
| 기능 ID / 화면 ID | CONC-001 / SCR-DASHBOARD |
| 사용자 스토리 | 투자자로서, 내 포트폴리오가 특정 테마에 얼마나 의존적인지 알고 싶다 |
| 입력 | portfolio_id, 포트폴리오 내 모든 종목의 theses |
| 처리(주 흐름) | ① `GET /api/portfolios/{id}/concentration` 호출 → ② C가 여러 종목의 key_assumptions를 의미 기반(임베딩)으로 비교해 공통 전제(테마) 탐지 → ③ 테마별 관련 종목·의존도(%) 산정 → ④ `analysis_results`(analysis_type=THESIS_CONCENTRATION)에 저장 |
| 출력 | concentration_theme(예: "AI CAPEX Growth"), concentration_score(%), affected_holdings 목록 |
| 예외 | 종목이 1개뿐이거나 공통 전제가 없음 → "집중 테마 없음"으로 표시 |
| 상태 | 대기 → 분석중 → 완료 |
| 인수 기준 | Given 3개 이상 종목의 Thesis가 있을 때, When 집중도 분석을 실행하면, Then 공통 테마와 관련 종목·의존도가 표시된다 |

## 4. 상태 전이 (핵심 흐름)

```
[Thesis 등록] → 구조화중 → 등록완료
     ↓ (신규 정보 트리거)
   수집중 → 분석중 → (증거 부족 시 Additional Research 루프)
     ↓
   Bull/Bear/Judge 판정 → thesis_versions 새 버전 기록
     ↓
   Alert Decision → (CRITICAL/MAJOR: 즉시 발송) / (MINOR: 주간 요약 큐) / (NONE: 미발송)
```

## 5. 화면 목록

- **SCR-AUTH**: 회원가입/로그인
- **SCR-PORTFOLIO**: 포트폴리오 생성·종목 관리·리밸런싱
- **SCR-THESIS-INPUT**: 투자 논리 자연어 입력 및 구조화 결과 확인/수정
- **SCR-DASHBOARD**: Portfolio 요약, Allocation, Thesis Status 카드, Recent Changes, Concentration, Risk
- **SCR-THESIS-HISTORY**: 최초 매수 이유 vs 현재 논리 비교, Confidence 시계열 그래프
- **SCR-QUERY**: 자연어 포트폴리오 질의 챗봇
- **SCR-ALERTS**: 알림 목록 및 설정(즉시/주간 요약 on-off)

## 6. 비기능 요구사항 (요약)

| 항목 | 기준 |
|---|---|
| 근거 필수 | 모든 SUPPORT/CONTRADICT 판정은 source_url·content_snippet을 동반 |
| 인증 | JWT 기반, 사용자별 포트폴리오 접근 제어 |
| API 계약 | 요청/응답 JSON은 snake_case로 통일(A↔B 변환 로직 불필요) |

## 7. 미해결 사항

- Thesis Concentration의 "의미 기반 공통 전제 탐지" 임베딩 유사도 임계치 → 벤치 후 확정 `[확인 필요]`.
- 주간 요약 이메일 발송 요일/시간 정책 → B 확정 필요.
- Additional Research 루프 최대 반복 횟수 → C 확정 필요(무한 루프 방지).

본 문서는 '무엇이 동작해야 하는가'까지만 다룬다. 모델·인프라 선택은 TDD/ADR에서 결정한다.
