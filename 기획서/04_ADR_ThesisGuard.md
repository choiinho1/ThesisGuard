# ADR — ThesisGuard

> 하나의 중요 기술 결정 = 1개 레코드. 각 ADR은 상태·맥락·결정·대안·결과로 작성했습니다(Michael Nygard 표준). `ThesisGuard_Team_Guide.md`에 이미 명시된 결정은 "수락됨"으로, 가이드에서 "A 또는 B" 식으로 열어둔 결정은 "제안됨"으로 표시해 팀 논의가 필요함을 표시했습니다.

## ADR-0001 · Agent 오케스트레이션: LangGraph 채택

| 항목 | 내용 |
|---|---|
| 상태 | 대체됨 · 2026-07-15 · ADR-0005 |
| 결정자 | C(AI/Agent Core) |

**맥락 (Context)**
ThesisGuard의 핵심은 Request Router → Research(3개 Agent 병렬) → Evidence Extraction/Classification → Bull → Bear → Judge → (조건부 Additional Research 루프) → Thesis Update → Portfolio Analysis → Alert Decision으로 이어지는, 조건 분기와 병렬 실행이 섞인 복잡한 워크플로다. 단순 프롬프트 체인으로는 "증거 부족 시 재수집 루프" 같은 상태 기반 분기를 표현하기 어렵다.

**결정 (Decision)**
우리는 Agent 오케스트레이션에 LangGraph를 사용하고, `AnalysisState` TypedDict로 그래프 전체의 상태를 관리한다.

**고려한 대안 (Considered Options)**

| 대안 | 장점 | 단점 |
|---|---|---|
| LangGraph (채택) | 조건 분기·병렬 노드·루프를 명시적으로 표현, LangSmith와 통합 평가 용이 | 러닝커브, 3인 중 C만 깊이 이해하면 병목 위험 |
| 단순 LangChain 체인 | 구현 단순 | 조건부 루프·병렬 Research Agent 표현 어려움 |
| 커스텀 상태머신(직접 구현) | 완전한 제어 | 처음부터 구현·검증 부담이 큼, 학기 일정에 부적합 |

**결과 (Consequences)**
좋아지는 것: Additional Research 루프, Filing/News/Macro 병렬 실행을 그래프로 명확히 표현 가능.
감수: C 외 팀원이 그래프 내부를 디버깅하기 어려울 수 있음 → `agents/graph.py` 진입점과 `ThesisAnalysisResult` 반환 계약만 B/A가 알면 되도록 경계를 명확히 함.
새 리스크: LangGraph 버전 업그레이드 시 API 변경 가능성 → 버전 고정(`requirements.txt` pin).

---

## ADR-0002 · Vector DB: pgvector 제안 (Qdrant 대안)

| 항목 | 내용 |
|---|---|
| 상태 | 제안됨 · 2026-07-10 — **팀 논의 후 최종 확정 필요** (가이드에는 "pgvector 또는 Qdrant"로 열려 있음) |
| 결정자 | B(Backend & Data Infra) `[확인 필요: 팀 합의]` |

**맥락 (Context)**
`sec_filings`/`ir_documents`/`earnings_materials`/`news_documents` 4개 컬렉션에 문서 임베딩을 저장하고, C의 Filing/News Agent가 RAG로 조회해야 한다. 메인 DB는 이미 PostgreSQL(Alembic 관리)이며, 3인 소규모 팀이라 운영 부담을 늘리지 않는 것이 중요하다.

**결정 (Decision)**
(제안) 우리는 벡터 검색에 pgvector를 사용해 기존 PostgreSQL 인스턴스에 통합한다. 데이터 규모가 커지고 검색 성능이 병목이 되면 Qdrant로 이관하는 별도 ADR을 작성한다.

**고려한 대안 (Considered Options)**

| 대안 | 장점 | 단점 |
|---|---|---|
| pgvector (제안) | 기존 Postgres·Alembic 마이그레이션과 통합, 별도 인프라 불필요 | 초대규모 벡터 검색 성능은 전용 벡터DB보다 낮음 |
| Qdrant | 대규모 벡터 검색 성능·전용 기능(필터링 등) 우수 | 별도 서버 운영 필요, 3인 팀 인프라 부담 증가 |

**결과 (Consequences)**
좋아지는 것(채택 시): 초기 구축 속도, 운영 단순화.
감수: PBL 프로젝트 특성상 문서량이 적어 pgvector 성능 한계는 크게 문제되지 않을 것으로 예상되나 실측 필요 `[확인 필요]`.
새 리스크: 팀이 Qdrant를 선호할 경우 본 ADR을 대체(Superseded)하는 새 ADR 작성 필요.

---

## ADR-0003 · Thesis 판정 방식: Bull vs Bear vs Judge Agentic Debate 채택

| 항목 | 내용 |
|---|---|
| 상태 | 수락됨 · 2026-07-10 (가이드에 명시된 기존 결정) |
| 결정자 | C(AI/Agent Core) |

**맥락 (Context)**
신규 증거가 기존 Thesis를 지지/반박하는지 단일 LLM 호출로 바로 판정하면, 한쪽 관점(예: 긍정적 뉴스에만 치우친 해석)으로 편향되기 쉽고 "왜 그렇게 판단했는지" 설명력이 약하다. ThesisGuard의 핵심 가치는 "설명 가능한" 검증이다.

**결정 (Decision)**
우리는 Bull Agent(지지 논거 생성)와 Bear Agent(반박 논거 생성)를 독립적으로 실행한 뒤, Judge Agent가 두 리포트를 종합해 최종 `updated_confidence`·`updated_status`·`change_reason`을 산정하는 Agentic Debate 구조를 채택한다.

**고려한 대안 (Considered Options)**

| 대안 | 장점 | 단점 |
|---|---|---|
| Bull/Bear/Judge (채택) | 상반된 관점을 명시적으로 대조, 설명 가능성·편향 감소 | LLM 호출 3회로 비용·지연 증가 |
| 단일 LLM 종합 판정 | 빠르고 저렴 | 편향 위험, "왜"에 대한 설명력 약함 |

**결과 (Consequences)**
좋아지는 것: PRD의 핵심 지표인 Citation Groundedness·Contradiction Detection Accuracy 확보에 유리.
감수: holding 1건 분석당 LLM 호출·토큰 비용이 늘어남 → PRD 7절의 "비용·지연" 벤치마크 필요.
새 리스크: Bull/Bear가 모두 극단적으로 편향된 리포트를 낼 경우 Judge도 왜곡될 수 있음 → Judge 프롬프트에 "증거 자체로 재검증" 지시 추가 검토.

---

## ADR-0005 · Thesis 점수: 템플릿 가중 결정론적 산정 채택

| 항목 | 내용 |
|---|---|
| 상태 | 수락됨 · 2026-07-15 |
| 결정자 | C(AI/Agent Core), B(Backend) 공동 |

**맥락 (Context)**
Judge Agent가 `updated_confidence`와 `updated_status`를 직접 생성하면 동일 근거에도 점수가
달라질 수 있고, 개별 핵심 가정이 최종 점수에 얼마나 기여했는지 감사하기 어렵다.

**결정 (Decision)**
Thesis 생성·논리 재설정 시 AI가 사전 정의된 유형 템플릿을 선택하고 사용자 가정을 템플릿
슬롯에 매핑한다. 분석 시 코드는 가정별 SUPPORT/CONTRADICT 영향도를 `0/0.5/1`로 변환해
상쇄하고, 템플릿의 고정 basis-point 가중치로 0~100 점수를 계산한다. 새 근거가 없는 가정은
이전 상태를 유지한다. Judge Agent는 Bull/Bear와 계산 내역을 바탕으로 설명만 생성하며 점수와
상태를 변경할 수 없다.

**결과 (Consequences)**
같은 입력에 같은 점수가 나오고, 슬롯별 가중치·상태·기여 점수를 API와 UI에서 확인할 수
있다. AI의 Evidence 분류 품질은 여전히 결과에 영향을 주므로 분류 평가셋은 계속 운영해야
한다. `BROKEN`은 점수와 분리해, Core 가정이 서로 다른 분석 회차에서 HIGH 반박으로 2회
연속 확인될 때만 발동한다. 발동 후에는 논리 재설정 전까지 상태를 유지한다.

---

## ADR-0004 · Alert 정책: thesis_status 기반 4단계 severity 매핑 채택

| 항목 | 내용 |
|---|---|
| 상태 | 수락됨 · 2026-07-10 (가이드에 명시된 기존 결정) |
| 결정자 | B(Backend), C(AI/Agent Core) 공동 |

**맥락 (Context)**
Thesis 상태가 바뀔 때마다 사용자에게 알림을 보내면 피로도가 커지고, 반대로 기준 없이 LLM이 자유롭게 "알릴지 말지"를 판단하면 일관성이 떨어진다. PRD 비목표에 "초단위 모니터링"이 없으므로 알림도 절제된 빈도가 필요하다.

**결정 (Decision)**
우리는 `thesis_status`(6단계)의 변화 폭을 `alert_severity`(CRITICAL/MAJOR/MINOR/NONE) 4단계로 규칙 기반 매핑하고, CRITICAL/MAJOR는 즉시 이메일, MINOR는 주간 요약, NONE은 미발송으로 처리한다.

**고려한 대안 (Considered Options)**

| 대안 | 장점 | 단점 |
|---|---|---|
| 규칙 기반 4단계 매핑 (채택) | 예측 가능·일관성, 사용자가 알림 기준을 이해하기 쉬움 | 세밀한 예외 상황(예: 여러 MINOR 변화의 누적)을 놓칠 수 있음 |
| LLM이 매번 자유 판단 | 맥락에 따른 유연한 판단 가능 | 비일관성, 같은 변화폭인데 다르게 판정될 위험 |

**결과 (Consequences)**
좋아지는 것: Alert Engine(B) 구현이 단순한 룩업 테이블로 가능, 사용자 신뢰도 확보.
감수: MINOR 변화가 누적되어도 개별적으로는 즉시 알림이 가지 않음 → 주간 요약에서 누적 반영되도록 Alert Engine 설계 필요.
새 리스크: 임계치(6단계 ↔ 4단계 매핑 규칙)를 잘못 정하면 과다/과소 알림 발생 → PRD 11절 미해결 질문으로 추적, 프로토타입 후 조정.

---

## ADR-000N · (신규 결정 템플릿)

새 결정이 생기면 아래 빈 양식을 복사해 ADR-000N으로 추가하세요.

| 항목 | 내용 |
|---|---|
| 상태 | 제안됨 / 수락됨 / 폐기됨 / 대체됨(→ADR-XXX) |
| 결정자 | |

**맥락 (Context)** — 이 결정을 필요하게 만든 상황·문제·제약.

**결정 (Decision)** — "우리는 ~한다" 능동태로.

**고려한 대안 (Considered Options)** — 대안 | 장점 | 단점 표 2~3개.

**결과 (Consequences)** — 좋아지는 것 / 감수할 단점 / 새 리스크.
