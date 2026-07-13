# PRD — ThesisGuard

> Notion 템플릿(PNU - 기획서 양식 > PRD)의 섹션 구조를 그대로 따랐습니다. `ThesisGuard_Team_Guide.md`를 근거로 작성했으며, 팀 논의로 확정해야 하는 수치·정책은 `[확인 필요]` 또는 `(미측정)`으로 표시했습니다.

## 문서 정보

| 항목 | 내용 |
|---|---|
| 상태 | Draft · v0.1 (기획 단계) |
| 작성자 / 오너 | ThesisGuard 팀 (A·B·C 공동, PM 역할 미지정 — `[확인 필요]`) |
| 핵심 팀 | Frontend(A) · Backend & Data Infra(B) · AI/Agent Core(C) |
| 목표 릴리스 | PBL 데모 발표일 기준 MVP (정확한 일자 `[확인 필요]`) |
| 관련 문서 | 기능정의서 · TDD · ADR · `ThesisGuard_Team_Guide.md` |

## TL;DR (요약)

사용자가 종목을 매수할 때 세운 **투자 논리(Thesis)**를 자연어로 입력하면, AI가 이를 Main Thesis·핵심 전제·긍정/부정 신호·리스크로 구조화해 기억한다. 이후 새로 나오는 SEC 공시·뉴스·거시지표를 자동 수집해 그 논리가 여전히 유효한지 근거와 함께 지속적으로 검증하고, 논리가 흔들리면 왜 흔들렸는지 설명하는 알림을 보낸다. MVP는 ① Thesis Change Detection ② Explainable Alert ③ Thesis Concentration Analysis 세 가지에 집중하며, 자동매매·매수매도 추천·초단위 모니터링은 다루지 않는다.

## 1. 배경 & 문제

**현상**: 개인 투자자는 종목을 살 때는 나름의 논리(예: "AI 데이터센터 투자 확대 수혜")를 세우지만, 시간이 지나면 그 논리를 기억하지 못하거나 새 뉴스·공시가 그 전제를 반박해도 눈치채지 못한다. 확증편향으로 반대 신호를 무시하는 경우도 많다.

**근거**: `ThesisGuard_Team_Guide.md`의 문제의식 — "내가 왜 투자했는지를 AI가 기억하고, 그 이유가 아직 유효한지를 새로운 정보가 나올 때마다 검증한다"에서 출발. 정량적 사용자 조사는 아직 없음 `[확인 필요: 팀 내 인터뷰/설문으로 보강]`.

**문제 정의**: 투자자는 (1) 자신의 매수 논리를 구조화해 기록할 도구가 없고, (2) 새로 나오는 정보가 그 논리를 강화하는지 약화하는지 근거 기반으로 판단할 수단이 없다.

## 2. 목표 & 성공 지표

**목표**: ① 자연어 투자 논리를 구조화해 기억한다. ② 신규 정보가 논리를 지지/반박하는지 근거와 함께 판단한다. ③ 포트폴리오 전체가 특정 테마에 과도하게 쏠려 있는지 알려준다.

| 지표 | 측정 방법 | 임계치 |
|---|---|---|
| Thesis Change Detection Accuracy | LangSmith 골든셋, 사람 라벨과의 일치율 | (미측정, 목표 80%+) |
| Evidence Classification Accuracy | SUPPORT/CONTRADICT/NEUTRAL/UNCERTAIN 라벨 일치율 | (미측정) |
| Citation Groundedness | 생성된 설명이 실제 근거 문서(evidence.content_snippet)에 기반하는 비율 | (미측정) |
| Contradiction Detection Accuracy | 논리와 충돌하는 증거를 놓치지 않는 재현율(recall) | (미측정) |
| 데모 통과 여부 | End-to-end 파이프라인 수동 체크 | PBL 발표일 기준 통과 |

## 3. 비목표 (Non-Goals)

자동매매 실행 · 매수/매도 추천(투자자문 행위) · 초단위·실시간 시세 모니터링 · 한국어 외 다국어 · 모바일 네이티브 앱(반응형 웹 우선) · 여러 사용자가 포트폴리오를 공동 편집하는 협업 기능.

## 4. 대상 사용자 & 사용자 스토리

| 페르소나 | 상황 | 핵심 니즈 |
|---|---|---|
| 장기 가치투자자 | 종목별 매수 논리는 세우지만 지속 추적이 번거로움 | 논리 변화를 자동으로 알려주는 시스템 |
| 테마/성장주 투자자 | 여러 종목이 같은 테마(예: AI CAPEX)에 몰려 있어 리스크 인지가 어려움 | 포트폴리오 테마 집중도 진단 |
| 바쁜 직장인 투자자 | 매일 모든 뉴스·공시를 확인할 시간이 없음 | 중요한 변화만 걸러주는 알림 |

- **US-1** 투자자로서, 종목을 매수한 이유를 자연어로 적으면 핵심 전제·긍정/부정 신호·리스크로 자동 구조화되길 원한다.
- **US-2** 투자자로서, 새 공시·뉴스가 내 논리를 강화하는지 약화하는지 근거와 함께 알고 싶다.
- **US-3** 투자자로서, 내 포트폴리오가 특정 테마에 얼마나 의존적인지 알고 싶다.
- **US-4** 투자자로서, 논리가 크게 흔들렸을 때만 즉시 이메일로 알림받고, 사소한 변화는 주간 요약으로 받고 싶다.

## 5. 핵심 사용자 흐름 (User Flow)

포트폴리오/종목 등록 → 투자 논리 자연어 입력 → AI가 Main Thesis/핵심 전제/긍정·부정 신호/리스크로 구조화 → 신규 공시·뉴스·거시데이터 수집(Filing/News/Macro Agent) → 증거 분류(SUPPORT/CONTRADICT/NEUTRAL/UNCERTAIN) → Bull vs Bear vs Judge 토론 → Thesis 업데이트(상태·Confidence 갱신) → 심각도에 따라 즉시/주간 알림 발송 → 대시보드에서 히스토리·근거 확인.

## 6. 기능 요구사항

| ID | 기능 | 우선순위 |
|---|---|---|
| F-1 | 포트폴리오/보유종목 등록·관리(리밸런싱 포함) | P0 |
| F-2 | 투자 논리 자연어 입력 → 자동 구조화 | P0 |
| F-3 | 신규 정보 수집(공시/뉴스/거시) 및 Thesis 대조 분석 | P0 |
| F-4 | Thesis 변화 판정(6단계) 및 Confidence 산정 | P0 |
| F-5 | 설명형 Alert(무엇이 변했는가/충돌 전제/종합 판단) 및 이메일 발송 | P0 |
| F-6 | 포트폴리오 Thesis Concentration 분석(테마 의존도) | P0 |
| F-7 | Thesis History 비교 뷰(최초 논리 vs 현재, Confidence 시계열) | P1 |
| F-8 | 자연어 포트폴리오 질의 챗봇 | P1 |
| F-9 | 공통 위험(Common Risk) 탐지 | P1 |
| F-10 | Alert 설정(즉시 알림/주간 요약 on-off) | P2 |

## 7. AI 에이전트 요구사항

**자율 수준**: 워크플로형 LangGraph 그래프 — Request Router → Research(Filing/News/Macro Agent 병렬) → Evidence Extraction → Evidence Classification → Bull → Bear → Judge → (증거 부족 시 Additional Research 루프) → Thesis Update → Portfolio Analysis → Alert Decision. 자동매매 등 실행 행위는 하지 않고 분석·설명만 수행한다.

**권한 경계**: 항상 근거(citation)를 포함해 결론을 제시 / 외부 데이터는 B가 제공하는 MCP Tool을 통해서만 조회(직접 API 호출 금지) / 금지: 투자자문성 매수·매도 문구 생성, 근거 없는 단정.

**가드레일**: 근거 없는 SUPPORT/CONTRADICT 판정 금지 · 증거 부족 시 UNCERTAIN 처리 후 Additional Research 루프로 재수집 · 확정되지 않은 수치를 지어내지 않음.

**모델 전략**: LangChain/LangGraph 기반 멀티에이전트(Filing/News/Macro/Bull/Bear/Judge/Portfolio Agent). 구체 모델 선정은 TDD/ADR에서 결정 `[벤치 후 확정]`.

**Eval**: LangSmith 평가셋 — Evidence Classification Accuracy, Thesis Change Detection Accuracy, Tool Selection Accuracy, Citation Groundedness, Contradiction Detection Accuracy.

**비용·지연**: holding 1건 분석의 P95 지연 목표·건당 토큰 비용 상한 `[확인 필요, 벤치 후 결정]`.

**실패 폴백**: 개별 MCP Tool 실패 시 해당 소스를 제외하고 나머지 근거로 분석 진행. 전체 실패 시 재시도 1회 후 실패하면 기존 Thesis 상태를 유지하고 사용자에게 안내.

## 8. 비기능 요구사항 (NFR)

**데이터 신뢰성**: 모든 근거(evidence)는 SEC 공시/IR/실적자료/뉴스/거시지표 등 출처와 `source_url`을 반드시 포함한다.

**성능**: 분석 요청 후 결과 반환까지 체감 지연을 관리한다 `[미측정]`.

**보안**: JWT 기반 인증, 사용자별 포트폴리오 접근 제어. 비밀번호는 해시 저장.

**협업 확장성**: 3인이 병렬 개발할 수 있도록 역할별 REST API(A↔B)·함수 계약(B↔C)으로 인터페이스를 고정한다.

## 9. 의존성 & 가정

**의존성**: SEC EDGAR, 시세 API, FRED 등 거시지표 API, LLM 제공자(외부 API 가정), PostgreSQL, Vector DB(pgvector 또는 Qdrant), SMTP(이메일 발송).

**가정**: 사용자는 최소 1개 이상의 종목과 투자 논리를 텍스트로 입력할 수 있다. 초단위 실시간 시세가 아닌 배치/트리거 기반의 준실시간 데이터로 충분하다(비목표 3절 참고).

## 10. 리스크 & 완화

- LLM이 근거 없이 판정(할루시네이션) → 근거 강제 + Additional Research 루프로 재검증.
- 외부 API(SEC/시세/거시) 장애·쿼터 제한 → MCP Tool 레이어에서 재시도/폴백, 실패한 소스는 제외하고 분석 지속.
- 3인 병렬 개발 중 API/DB 스키마 불일치 → 사전 계약(OpenAPI 스펙, `run_analysis_workflow` 시그니처) 고정, 변경 전 팀 채널 공지(협업 규칙 8번).
- 투자자문으로 오인될 위험 → 매수/매도 추천 문구를 절대 생성하지 않도록 프롬프트 가드레일 적용, 비목표에 명시.

## 11. 미해결 질문 (Open Questions)

| 질문 | 담당 | 기한 |
|---|---|---|
| Thesis 상태 6단계별 Confidence 점수 임계치를 어떻게 정할지 | C(AI) | 프로토타입 완성 후 |
| 알림 발송 주기(주간 요약 요일/시간) 정책 | B(Backend) | Alert Engine 구현 시 |
| 실제 사용할 LLM/임베딩 모델 선정 | C(AI) | 벤치마크 이후 |
| pgvector vs Qdrant 최종 선택 | B(Backend) | TDD/ADR 확정 시 (본 문서 ADR-0002 참고) |

## 12. 마일스톤 & 릴리스

| 단계 | 산출물 | 완료 기준 |
|---|---|---|
| M1 (핵심 등록) | 포트폴리오/종목/투자논리 등록 + Thesis 구조화 | 자연어 논리 입력 시 구조화된 필드(Main Thesis 등) 반환 |
| M2 (분석 루프) | 증거 수집·분류·Bull/Bear/Judge·Thesis 업데이트 | 신규 정보를 넣으면 Thesis 상태·Confidence가 근거와 함께 갱신됨 |
| M3 (Concentration + Alert) | 테마 집중도 분석 + 이메일 알림 | 심각도별 알림 발송, 대시보드에 반영 |
| M4 (데모) | 프론트 대시보드 통합 + PBL 발표 | 3대 대표 기능(Thesis Change Detection / Explainable Alert / Concentration Analysis) 시연 가능 |
