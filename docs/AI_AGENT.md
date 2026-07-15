# ThesisGuard AI Agent Core

`agents/`는 3인 팀 중 C(AI/Agent Core)가 소유한다. 팀 가이드의 F-2~F-6과
`run_analysis_workflow()` B-C 계약을 구현한다.

## 폴더 구조

```text
agents/
├── graph.py              # LangGraph 조립 및 공개 진입점
├── models.py             # B-C Pydantic 결과 계약과 DB enum
├── contracts.py          # B의 Context/MCP 포트, LLM 포트
├── model.py              # LangChain 구조화 출력과 프롬프트
├── runtime.py            # 주입 의존성과 정책 설정
├── state.py              # LangGraph AnalysisState
├── retrieval.py          # 규칙 기반 후보 선별과 공시 문단 축약
├── rag.py                # Multi-query Hybrid RAG, RRF, MMR, 인접 청크 확장
├── evidence_policy.py    # 판정에 사용할 유효 근거 기준
├── logic_graph.py        # Thesis별 인과 그래프 검증·전파
├── scoring.py            # 인과 그래프 기반 결정론적 점수 계산
├── policy.py             # 규칙 기반 Alert 등급
├── nodes/
│   ├── filing_agent.py
│   ├── news_agent.py
│   ├── macro_agent.py
│   ├── source_selector.py
│   ├── evidence.py
│   ├── debate.py
│   ├── portfolio.py
│   └── alert.py
└── evaluation/           # LangSmith 평가 레코드와 지표
```

## 분석 흐름

```text
Request Router
  -> Filing / News / Macro Agent (병렬)
  -> Source Selector (규칙 후보 선별 -> Hybrid RAG -> 소스 균형)
  -> Evidence Classification
     -> 근거 부족: Additional Research 1회
  -> Bull / Bear Agent + Deterministic Scoring + BROKEN Hard Gate (병렬)
  -> Judge Agent (계산 결과 설명만 생성)
  -> Portfolio Concentration + Common Risk
  -> Alert Decision
  -> ThesisAnalysisResult
```

`research_data`는 팀 계약대로 `filings`, `news`, `macro` 키를 가진 dict다. 병렬 노드가 같은
상태를 갱신하므로 `agents/state.py`의 reducer가 세 결과를 합친다.

News Agent는 SEC의 정식 회사명과 티커를 사용한 기본 검색과 핵심 가정별 검색을 병렬 실행한다.
경쟁·시장·실적 가정은 영어 금융 검색 힌트를 함께 사용하며, Bing News의 상세 RSS 설명을
우선 사용하고 결과가 없을 때 Google News로 대체한다. 공개 접근 가능한 발행사 페이지는
본문을 정제·축약해 사용하고, 동적 페이지·차단·유료벽이면 RSS 설명으로 대체한다. Source Selector는 회사명 일치, 뉴스
최신성, URL/제목 중복, Thesis 키워드 일치를 모델 호출 없이 계산하며 기본 점수
0.30 미만인 뉴스는 분류기에 보내지 않는다. 뉴스와 공시는 발행일이 확인되고 분석 시점
기준 30일 이내인 자료만 허용하며, 날짜가 없거나 30일을 넘거나 미래로 표시된 자료는
본문 다운로드와 분류 전에 제외한다. 허용 범위 안의 공시는 최신 10-Q·10-K·8-K를 우선
고른 뒤 관련도가 높은 문단만 최대 6,000자로 축약해 분류기에 전달한다.
재검색 라운드에서 이미 분류한 `document_id`는 기존 결과를 재사용한다.

RAG가 활성화되면 규칙 기반 선별 결과를 최종 개수의 3배까지 후보로 유지한 뒤 다음 순서로
재정렬한다.

1. 문서를 1,400자 단위(200자 중첩)로 나누고 Upstage 임베딩을 생성한다.
2. 핵심 가정·긍정/부정 신호·리스크를 최대 6개의 독립 검색 질의로 사용한다.
3. 제목과 본문을 함께 임베딩하고, Dense cosine 검색과 한국어/영어 BM25 검색 결과를 RRF로 결합한다.
4. Dense 점수가 각 질의 최고점의 20% 미만인 약한 후보를 제외한다.
5. 검색어 링크만 나열한 인덱스·아카이브 페이지는 저정보 문서로 제외한다.
6. 최고 RRF 점수의 65% 미만인 후보는 개수를 채우기 위해 억지로 선택하지 않는다.
7. MMR로 유사 기사 반복을 줄이면서 공시/뉴스/거시 소스 제한을 지킨다.
8. 선택 청크의 앞뒤 청크까지 확장해 문맥을 복원한 뒤 Evidence 분류기에 전달한다.

동일 원문은 SHA-256 기반 메모리 캐시에서 임베딩을 재사용한다. 임베딩 API 오류가 나거나
키가 없으면 분석을 중단하지 않고 기존 규칙 기반 Source Selector로 자동 전환한다. 현재 구현은
매 분석에서 새로 수집한 라이브 후보를 검색하는 구조이며, 과거 전체 문서 코퍼스의 영구 검색은
추후 pgvector 같은 저장소를 연결하는 별도 단계다.

검색 품질은 `agents/evaluation/datasets/investment_rag_v1.json` 골든셋과 RAGAS ID-Based Context
Precision/Recall, MRR, nDCG로 회귀 평가한다. 실행법과 현재 기준 점수는
`agents/evaluation/README.md`에 기록한다.

## 설치와 검증

```powershell
python -m pip install -e ".[dev]"
python -m black --check agents tests
python -m ruff check .
python -m pytest
```

## 백엔드 연결

B는 `backend/mcp_tools/` 함수들을 `ResearchTools` 프로토콜로 감싸고 시작 시 Agent를 구성한다.

```python
from agents.graph import ThesisGuardAgent, configure_agent, run_analysis_workflow
from agents.model import LangChainAnalysisModel

agent = ThesisGuardAgent(
    context_provider=BackendContextProvider(...),
    research_tools=BackendResearchTools(...),
    model=LangChainAnalysisModel(chat_model),
)
configure_agent(agent)

result = run_analysis_workflow(portfolio_id, holding_id)
payload = result.model_dump(mode="json")
```

FastAPI의 async 라우트에서는 이벤트 루프를 막지 않도록 `arun_analysis_workflow()`를 사용한다.

## 안전 정책

- C는 외부 데이터 API를 직접 호출하지 않고 B의 MCP 포트만 사용한다.
- 방향성 Evidence는 `source_url` 또는 `vector_doc_id`가 있어야 한다.
- 원문을 번호가 붙은 최대 500자 구간으로 나누고, 모델은 자유 인용문 대신 구간 번호를 선택한다.
- 유효하지 않은 원문 구간 번호를 선택한 경우에만 UNCERTAIN/LOW로 강등한다.
- 문서 전체를 읽은 뒤 모든 핵심 가정을 SUPPORT/CONTRADICT/MIXED/NOT_ADDRESSED로 각각
  판정한다. 경쟁 제품의 개발·시장 진입 계획도 `경쟁자 없음` 같은 절대 가정의 반박 신호로 본다.
- 검증용 원문 인용과 표시용 근거 설명을 분리한다. 모델은 최대 3개 원문 구간을 선택하고,
  표시용 설명은 핵심 사실·수치/기간·투자 논리와의 관계를 담은 한국어 2~3문장, 500자 이내로 제한한다.
- 표시용 한국어 요약 생성 실패는 유효한 분류·영향도 판정을 폐기하지 않는다.
- 관련도가 0.55 미만인 방향성 판정은 NEUTRAL/LOW로 강등한다.
- SUPPORT/CONTRADICT이면서 Impact가 MEDIUM/HIGH인 근거만 Bull/Bear에 전달한다.
- 점수 엔진은 모든 정보×가정 노드 조합을 만들고 방향×영향도×관련도로 signed strength를
  계산한다. 같은 방향의 여러 근거는 한계효과가 감소하는 고정식으로 결합한 뒤 저장된
  인과 그래프의 `AND`/`OR`/`CONTRIBUTING` 규칙으로 루트 상태를 계산한다.
- 각 정보의 최종 점수 변화는 결정론적 Shapley 귀속으로 계산하며, 귀속값 합계는 실제
  분석 회차의 점수 변화와 일치한다.
- 새 방향성 근거가 없는 가정은 저장된 이전 상태를 유지한다.
- 특정 가정에 대한 언급 부재는 반박이 아니라 `NOT_ADDRESSED`다. 노드별 원문 구간을
  인용하지 않은 SUPPORT/CONTRADICT 판정은 신뢰 코드가 강도 0으로 제외한다.
- Judge는 계산된 점수·상태를 수정할 수 없고 설명만 생성한다. Judge가 실패해도 결정론적
  점수는 유지한다.
- 집중도 퍼센트는 LLM 값 대신 실제 보유 비중 합계로 다시 계산한다.
- Alert는 LLM이 아니라 `policy.py` 규칙으로 결정한다.
- 매수·매도 및 자동매매 추천을 생성하지 않는다.

세부 스키마는 [schema.md](schema.md), B-C 호출 계약은 [api.md](api.md)를 참고한다.
