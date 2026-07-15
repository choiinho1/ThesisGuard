"""Versioned, deterministic templates for investment-thesis assumptions.

The model selects a template and maps user statements to its slots, but it must
not alter the template weights. The selected template becomes effective
automatically whenever a thesis is created or its raw logic is reset. Weights
are stored as integer basis points so scoring is stable across runtimes and
serialization formats.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, model_validator

THESIS_TEMPLATE_CATALOG_VERSION = "1.0.0"
WEIGHT_BASIS_POINTS = 10_000


class ThesisTemplateId(StrEnum):
    GENERAL_FUNDAMENTAL = "GENERAL_FUNDAMENTAL"
    SCALABLE_GROWTH = "SCALABLE_GROWTH"
    QUALITY_COMPOUNDER = "QUALITY_COMPOUNDER"
    MARGIN_EXPANSION = "MARGIN_EXPANSION"
    TURNAROUND = "TURNAROUND"
    CYCLICAL_RECOVERY = "CYCLICAL_RECOVERY"
    CATALYST_EVENT = "CATALYST_EVENT"
    ASSET_VALUE_RERATING = "ASSET_VALUE_RERATING"
    INCOME_DISTRIBUTION = "INCOME_DISTRIBUTION"


class AssumptionSlot(BaseModel):
    """One semantic assumption slot within a thesis template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label_ko: str = Field(min_length=1)
    weight_bps: int = Field(gt=0, le=WEIGHT_BASIS_POINTS)
    core: bool = False
    verification_question: str = Field(min_length=1)
    suggested_metrics: tuple[str, ...] = Field(min_length=1)
    invalidation_rule_hint: str = Field(min_length=1)

    @property
    def weight_percent(self) -> float:
        return self.weight_bps / 100


class ThesisTypeTemplate(BaseModel):
    """An immutable scoring template selected before evidence is evaluated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: ThesisTemplateId
    name_ko: str = Field(min_length=1)
    description: str = Field(min_length=1)
    use_when: tuple[str, ...] = Field(min_length=1)
    avoid_when: tuple[str, ...] = Field(min_length=1)
    assumption_slots: tuple[AssumptionSlot, ...] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def validate_template_invariants(self) -> ThesisTypeTemplate:
        slot_ids = [slot.slot_id for slot in self.assumption_slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("Template assumption slot IDs must be unique")
        if sum(slot.weight_bps for slot in self.assumption_slots) != WEIGHT_BASIS_POINTS:
            raise ValueError("Template weights must total exactly 10,000 basis points")
        core_count = sum(slot.core for slot in self.assumption_slots)
        if not 1 <= core_count <= 2:
            raise ValueError("A template must have one or two core assumption slots")
        return self


def _slot(
    slot_id: str,
    label_ko: str,
    weight_bps: int,
    *,
    core: bool,
    verification_question: str,
    suggested_metrics: tuple[str, ...],
    invalidation_rule_hint: str,
) -> AssumptionSlot:
    return AssumptionSlot(
        slot_id=slot_id,
        label_ko=label_ko,
        weight_bps=weight_bps,
        core=core,
        verification_question=verification_question,
        suggested_metrics=suggested_metrics,
        invalidation_rule_hint=invalidation_rule_hint,
    )


_TEMPLATES = (
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.GENERAL_FUNDAMENTAL,
        name_ko="일반 펀더멘털",
        description="특정 촉매보다 수요, 경쟁력, 수익성, 재무 건전성의 균형에 근거한 기본형",
        use_when=(
            "주된 가치 창출 경로가 하나의 특수 유형으로 명확히 분류되지 않을 때",
            "여러 펀더멘털 요인을 균형 있게 추적하려 할 때",
        ),
        avoid_when=("명확한 턴어라운드, 경기 사이클 또는 단일 이벤트가 논리의 중심일 때",),
        assumption_slots=(
            _slot(
                "demand",
                "수요의 지속성",
                2500,
                core=True,
                verification_question="제품·서비스에 대한 최종 수요가 Thesis 기간 동안 유지되는가?",
                suggested_metrics=("매출 성장률", "수주·백로그", "고객 수·사용량"),
                invalidation_rule_hint="수요 지표가 사용자가 정한 하한을 정해진 기간 연속 하회",
            ),
            _slot(
                "competitive_position",
                "경쟁 지위",
                2500,
                core=True,
                verification_question="회사가 경쟁사 대비 가격·제품·유통 우위를 유지하는가?",
                suggested_metrics=("시장점유율", "가격 프리미엄", "고객 유지율"),
                invalidation_rule_hint="점유율 또는 유지율이 정해진 허용폭을 지속적으로 하회",
            ),
            _slot(
                "economics",
                "수익성과 현금 창출",
                2500,
                core=False,
                verification_question="성장이 이익과 현금흐름으로 전환되는가?",
                suggested_metrics=("영업마진", "잉여현금흐름", "투하자본수익률"),
                invalidation_rule_hint="마진·현금흐름이 사전 정의된 경로에서 중대하게 이탈",
            ),
            _slot(
                "financial_resilience",
                "재무 건전성과 실행력",
                2500,
                core=False,
                verification_question="회사가 계획을 실행할 재무 여력과 운영 역량을 보유했는가?",
                suggested_metrics=("순부채", "이자보상배율", "가이던스 달성률"),
                invalidation_rule_hint="유동성 하한 위반 또는 핵심 실행 일정의 중대한 반복 지연",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.SCALABLE_GROWTH,
        name_ko="확장형 성장",
        description="큰 시장에서 채택과 점유율이 확대되고 규모의 경제로 수익성이 개선된다는 논리",
        use_when=(
            "매출·사용자·거래량의 고성장이 핵심일 때",
            "현재 이익보다 미래 규모와 단위경제성 개선이 중요할 때",
        ),
        avoid_when=("성장이 이미 안정화된 성숙 기업", "단기 비용 절감만이 논리의 중심인 경우"),
        assumption_slots=(
            _slot(
                "market_demand",
                "시장 수요 확대",
                3000,
                core=True,
                verification_question="회사가 겨냥한 시장과 실제 수요가 충분히 빠르게 확대되는가?",
                suggested_metrics=("시장 성장률", "매출 성장률", "사용량 증가율"),
                invalidation_rule_hint="핵심 수요 지표가 성장 하한을 정해진 기간 연속 하회",
            ),
            _slot(
                "adoption_share",
                "채택과 점유율 확대",
                3000,
                core=True,
                verification_question="회사가 성장 시장에서 고객과 점유율을 실제로 확보하는가?",
                suggested_metrics=("신규 고객", "시장점유율", "순매출 유지율"),
                invalidation_rule_hint="시장 성장에도 회사의 채택·점유율 지표가 지속 하락",
            ),
            _slot(
                "unit_economics",
                "단위경제성과 수익화",
                2500,
                core=False,
                verification_question="규모 확대가 단위당 경제성과 장기 마진을 개선하는가?",
                suggested_metrics=("총마진", "고객획득비용 회수기간", "공헌이익"),
                invalidation_rule_hint="성장에도 단위경제성이 정해진 개선 경로를 반복 이탈",
            ),
            _slot(
                "funding_execution",
                "자금 여력과 실행",
                1500,
                core=False,
                verification_question="목표 규모에 도달할 때까지 필요한 자금과 실행력이 충분한가?",
                suggested_metrics=("현금 소진율", "현금 런웨이", "제품·설비 일정"),
                invalidation_rule_hint="필요 런웨이 하한 위반 또는 핵심 일정의 중대한 지연",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.QUALITY_COMPOUNDER,
        name_ko="고품질 복리 성장",
        description="지속 가능한 경쟁우위와 높은 자본수익률이 장기간 복리 성장을 만든다는 논리",
        use_when=("이미 수익성이 검증된 기업", "장기 재투자와 경쟁우위가 논리의 중심일 때"),
        avoid_when=("초기 적자 성장 기업", "단일 이벤트 성패가 투자 결과를 좌우할 때"),
        assumption_slots=(
            _slot(
                "demand_durability",
                "수요의 내구성",
                2500,
                core=False,
                verification_question="반복 수요와 고객 충성도가 장기간 유지되는가?",
                suggested_metrics=("반복매출 비중", "유지율", "경기 조정 매출 성장"),
                invalidation_rule_hint="유지율·반복매출이 구조적으로 하락하고 회복 기준을 미달",
            ),
            _slot(
                "moat",
                "경쟁우위의 지속성",
                3000,
                core=True,
                verification_question="가격 결정력, 전환비용 또는 네트워크 효과가 유지되는가?",
                suggested_metrics=("가격·물량 분해", "점유율", "고객 이탈률"),
                invalidation_rule_hint="가격 결정력 또는 시장 지위가 정해진 허용폭을 지속 하회",
            ),
            _slot(
                "reinvestment_quality",
                "재투자 수익성",
                3000,
                core=True,
                verification_question="추가 투자된 자본이 높은 증분 수익을 만들어내는가?",
                suggested_metrics=("증분 투하자본수익률", "재투자율", "영업이익 성장률"),
                invalidation_rule_hint="증분 자본수익률이 장기간 사전 정의된 하한을 하회",
            ),
            _slot(
                "capital_allocation",
                "재무 건전성과 자본배분",
                1500,
                core=False,
                verification_question="경영진이 잉여현금을 가치 창출적으로 배분하는가?",
                suggested_metrics=("순부채", "인수 수익성", "자사주 매입 단가 규율"),
                invalidation_rule_hint="과도한 레버리지 또는 반복적인 가치 훼손 자본배분 발생",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.MARGIN_EXPANSION,
        name_ko="마진 개선",
        description="매출 안정과 비용 구조 개선이 영업 레버리지 및 현금흐름 확대로 이어진다는 논리",
        use_when=("비용 절감, 믹스 개선, 가격 인상 또는 규모의 경제가 핵심일 때",),
        avoid_when=("매출 성장 자체가 핵심", "비용 개선이 일회성 회계 효과에만 의존할 때"),
        assumption_slots=(
            _slot(
                "revenue_resilience",
                "매출 기반의 안정성",
                2000,
                core=False,
                verification_question="마진 개선 과정에서 매출과 고객 기반이 유지되는가?",
                suggested_metrics=("유기적 매출 성장", "판매량", "고객 유지율"),
                invalidation_rule_hint="비용 절감과 동시에 수요 지표가 허용 범위를 초과해 악화",
            ),
            _slot(
                "gross_margin_driver",
                "총마진 개선 동력",
                3000,
                core=True,
                verification_question=(
                    "가격, 제품 믹스 또는 원가 개선이 총마진을 지속적으로 높이는가?"
                ),
                suggested_metrics=("총마진", "가격·물량·믹스", "단위원가"),
                invalidation_rule_hint="총마진이 목표 경로를 정해진 기간 연속 하회",
            ),
            _slot(
                "operating_leverage",
                "영업 레버리지",
                3000,
                core=True,
                verification_question="매출 증가 또는 비용 절감이 영업이익에 더 크게 반영되는가?",
                suggested_metrics=("영업마진", "판관비율", "증분 영업마진"),
                invalidation_rule_hint="증분 영업마진 또는 비용률이 사전 정의된 개선 기준을 미달",
            ),
            _slot(
                "cash_conversion",
                "현금 전환과 지속성",
                2000,
                core=False,
                verification_question="회계상 이익 개선이 반복 가능한 현금흐름으로 전환되는가?",
                suggested_metrics=("잉여현금흐름 마진", "현금전환율", "일회성 비용"),
                invalidation_rule_hint="현금전환율 하한 미달 또는 절감 효과의 중대한 반전",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.TURNAROUND,
        name_ko="턴어라운드",
        description=(
            "악화된 사업의 안정화, 실행 개선과 유동성 확보가 "
            "정상 수익력 회복으로 이어진다는 논리"
        ),
        use_when=(
            "실적·운영이 이미 악화됐고 정상화가 핵심일 때",
            "새 경영진 또는 구조조정 계획이 있을 때",
        ),
        avoid_when=("사업이 이미 정상화된 기업", "외부 경기 회복만을 기대하는 경우"),
        assumption_slots=(
            _slot(
                "stabilization",
                "사업 악화의 안정화",
                2500,
                core=False,
                verification_question="매출, 고객, 품질 또는 생산성 악화가 멈췄는가?",
                suggested_metrics=("매출 감소폭", "고객 이탈", "재고·품질 지표"),
                invalidation_rule_hint="핵심 운영 지표의 악화가 정해진 기간 계속 가속",
            ),
            _slot(
                "execution_milestones",
                "개선 계획의 실행",
                3000,
                core=True,
                verification_question="경영진이 비용, 제품, 조직 개선 일정을 실제로 달성하는가?",
                suggested_metrics=("구조조정 이행률", "비용 절감 실현액", "제품 일정"),
                invalidation_rule_hint="핵심 마일스톤의 취소 또는 반복적인 중대 지연",
            ),
            _slot(
                "liquidity_runway",
                "유동성과 생존 여력",
                3000,
                core=True,
                verification_question="정상화 전까지 부채와 현금 소진을 감당할 수 있는가?",
                suggested_metrics=("현금 런웨이", "차입 만기", "이자보상배율"),
                invalidation_rule_hint="최소 런웨이 하한 위반, 차환 실패 또는 약정 위반",
            ),
            _slot(
                "earnings_recovery",
                "수요와 정상 수익력 회복",
                1500,
                core=False,
                verification_question="안정화가 실제 매출·마진·현금흐름 회복으로 연결되는가?",
                suggested_metrics=("정상화 영업마진", "수주", "영업현금흐름"),
                invalidation_rule_hint="회복 기간 내 수익성 지표가 최소 경로를 달성하지 못함",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.CYCLICAL_RECOVERY,
        name_ko="경기·산업 사이클 회복",
        description="재고, 공급, 가격 또는 거시 사이클의 변곡이 실적 회복으로 전달된다는 논리",
        use_when=("반도체, 원자재, 운송, 산업재처럼 업황 순환성이 클 때",),
        avoid_when=("기업 고유의 구조적 성장 또는 내부 개선이 주된 동력일 때",),
        assumption_slots=(
            _slot(
                "cycle_inflection",
                "사이클 변곡",
                3500,
                core=True,
                verification_question="재고·주문·가격 지표가 실제 회복 국면으로 전환됐는가?",
                suggested_metrics=("재고일수", "신규 주문", "산업 가격지수"),
                invalidation_rule_hint="예상 변곡 기간이 지나도 선행 지표가 회복 기준을 미달",
            ),
            _slot(
                "volume_pricing",
                "물량과 가격의 실적 전달",
                2500,
                core=True,
                verification_question="산업 회복이 회사의 판매량과 실현 가격으로 이어지는가?",
                suggested_metrics=("출하량", "평균판매가격", "가동률"),
                invalidation_rule_hint="산업 지표 회복에도 회사의 물량·가격이 허용폭 이상 부진",
            ),
            _slot(
                "capacity_cost",
                "공급 규율과 비용 위치",
                2000,
                core=False,
                verification_question="공급 증가가 제한되고 회사가 원가 경쟁력을 유지하는가?",
                suggested_metrics=("산업 증설률", "회사 가동률", "단위 생산원가"),
                invalidation_rule_hint="공급 과잉 재개 또는 회사 원가 위치의 구조적 악화",
            ),
            _slot(
                "balance_sheet",
                "하락기 생존력",
                2000,
                core=False,
                verification_question="회복이 늦어져도 회사가 재무적으로 버틸 수 있는가?",
                suggested_metrics=("순부채", "고정비 부담", "유동성"),
                invalidation_rule_hint="유동성 하한 위반 또는 회복 전 자본 훼손 위험 현실화",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.CATALYST_EVENT,
        name_ko="촉매·이벤트",
        description=(
            "승인, 임상, 제품 출시, 소송, 인수합병 등 명시적 사건의 "
            "성공과 경제적 효과에 근거한 논리"
        ),
        use_when=("결과와 일정이 비교적 명확한 단일 또는 연속 이벤트가 핵심일 때",),
        avoid_when=(
            "장기간의 일반적인 펀더멘털 개선이 핵심",
            "관측 가능한 마일스톤이 없는 막연한 기대",
        ),
        assumption_slots=(
            _slot(
                "event_outcome",
                "핵심 이벤트의 성립",
                3500,
                core=True,
                verification_question="사전 정의된 승인·임상·거래·출시 조건이 충족됐는가?",
                suggested_metrics=("공식 결정", "임상 1차 평가지표", "거래 종결 조건"),
                invalidation_rule_hint="공식 실패·불허·취소 또는 사전 정의된 성공 기준 미달",
            ),
            _slot(
                "prerequisites_timing",
                "선행 조건과 일정",
                2000,
                core=False,
                verification_question="필수 선행 절차와 일정이 계획대로 진행되는가?",
                suggested_metrics=("마일스톤 완료", "규제 일정", "파트너 이행"),
                invalidation_rule_hint="핵심 선행 조건 실패 또는 허용 기한을 넘는 중대 지연",
            ),
            _slot(
                "economic_payoff",
                "경제적 효과",
                2500,
                core=True,
                verification_question="이벤트 성공이 회사 가치 동인과 현금흐름에 충분히 중요한가?",
                suggested_metrics=("예상 매출 기여", "비용 절감", "순현금 유입"),
                invalidation_rule_hint="성공하더라도 경제적 효과가 사전 정의된 최소 기준을 미달",
            ),
            _slot(
                "runway_downside",
                "실패 시 하방과 자금 여력",
                2000,
                core=False,
                verification_question="지연 또는 실패 시에도 재무적 생존과 잔존가치가 유지되는가?",
                suggested_metrics=("현금 런웨이", "대체 파이프라인", "해지·손해 비용"),
                invalidation_rule_hint="이벤트 전 자금 고갈 또는 실패 시 잔존가치 기준 훼손",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.ASSET_VALUE_RERATING,
        name_ko="저평가 해소·자산가치 실현",
        description=(
            "정상 이익 또는 보유 자산의 가치가 촉매와 자본배분을 통해 " "시장에 실현된다는 논리"
        ),
        use_when=("순자산, 정상 이익, 사업부 합산가치 대비 할인 해소가 핵심일 때",),
        avoid_when=(
            "단순히 주가가 과거보다 낮다는 이유만 있는 경우",
            "가치 실현 경로가 전혀 없는 경우",
        ),
        assumption_slots=(
            _slot(
                "underlying_value",
                "기초 자산·정상 이익의 가치",
                3000,
                core=True,
                verification_question=(
                    "주장하는 자산가치나 정상 이익이 검증 가능하고 지속 가능한가?"
                ),
                suggested_metrics=("정상화 현금흐름", "순자산가치", "사업부별 이익"),
                invalidation_rule_hint=(
                    "자산 손상 또는 정상 이익 추정의 핵심 전제가 기준 이하로 하락"
                ),
            ),
            _slot(
                "realization_catalyst",
                "가치 실현 촉매",
                3000,
                core=True,
                verification_question="할인을 줄일 매각, 분할, 개선 또는 공시 촉매가 실행되는가?",
                suggested_metrics=("자산 매각", "사업 분할", "수익성 정상화 일정"),
                invalidation_rule_hint="핵심 촉매의 공식 철회 또는 허용 기간 내 진전 부재",
            ),
            _slot(
                "capital_governance",
                "자본배분과 지배구조",
                2000,
                core=False,
                verification_question="경영진과 지배구조가 가치를 주주에게 귀속시키는가?",
                suggested_metrics=("자사주·배당", "관련자 거래", "인수·매각 조건"),
                invalidation_rule_hint="가치 훼손 자본배분 또는 중대한 이해상충이 반복 발생",
            ),
            _slot(
                "hidden_liabilities",
                "숨은 부채와 하방",
                2000,
                core=False,
                verification_question="부채, 세금, 소송, 연금 등 가치 차감 요인이 통제되는가?",
                suggested_metrics=("순부채", "우발부채", "연금·환경 의무"),
                invalidation_rule_hint="미반영 부채가 사전 정의한 가치 완충폭을 초과",
            ),
        ),
    ),
    ThesisTypeTemplate(
        template_id=ThesisTemplateId.INCOME_DISTRIBUTION,
        name_ko="현금분배·인컴",
        description=(
            "안정적인 현금흐름과 건전한 재무구조가 배당·분배의 지속 및 " "성장을 뒷받침한다는 논리"
        ),
        use_when=("배당, 분배금 또는 자사주 환원이 투자 논리의 중심일 때",),
        avoid_when=("높은 표면 수익률만 있고 현금흐름 커버리지가 약한 경우",),
        assumption_slots=(
            _slot(
                "cashflow_stability",
                "현금흐름의 안정성",
                3000,
                core=True,
                verification_question="분배의 원천인 영업·가용 현금흐름이 안정적인가?",
                suggested_metrics=("영업현금흐름", "가용현금흐름", "현금흐름 변동성"),
                invalidation_rule_hint="가용 현금흐름이 사전 정의된 안정성 하한을 지속 하회",
            ),
            _slot(
                "distribution_coverage",
                "분배 커버리지",
                3000,
                core=True,
                verification_question="배당·분배가 반복 가능한 현금흐름으로 충분히 충당되는가?",
                suggested_metrics=("배당성향", "분배 커버리지", "잉여현금흐름 대비 환원"),
                invalidation_rule_hint="커버리지 하한 위반 또는 차입에 의존한 분배가 지속",
            ),
            _slot(
                "balance_sheet",
                "재무구조와 재투자 여력",
                2500,
                core=False,
                verification_question="분배 후에도 부채 상환과 필수 재투자가 가능한가?",
                suggested_metrics=("순부채 배수", "이자보상배율", "유지보수 투자"),
                invalidation_rule_hint="약정·레버리지 기준 위반 또는 필수 투자 부족 발생",
            ),
            _slot(
                "distribution_policy",
                "분배 정책과 이해관계 정렬",
                1500,
                core=False,
                verification_question="경영진의 정책과 행동이 지속 가능한 환원과 일치하는가?",
                suggested_metrics=("공식 배당정책", "배당 이력", "주식수 변화"),
                invalidation_rule_hint="정책 철회, 중대한 삭감 또는 상쇄적 희석이 발생",
            ),
        ),
    ),
)


THESIS_TEMPLATE_CATALOG = MappingProxyType(
    {template.template_id: template for template in _TEMPLATES}
)


def list_thesis_templates() -> tuple[ThesisTypeTemplate, ...]:
    """Return catalog templates in stable presentation order."""

    return _TEMPLATES


def get_thesis_template(template_id: ThesisTemplateId | str) -> ThesisTypeTemplate:
    """Resolve a template ID, rejecting unknown values instead of guessing."""

    normalized_id = ThesisTemplateId(template_id)
    return THESIS_TEMPLATE_CATALOG[normalized_id]


def build_thesis_template_snapshot(template_id: ThesisTemplateId | str) -> dict:
    """Create the immutable payload persisted with a thesis configuration."""

    template = get_thesis_template(template_id)
    return {
        "catalog_version": THESIS_TEMPLATE_CATALOG_VERSION,
        **template.model_dump(mode="json"),
    }


def thesis_template_selection_guide() -> str:
    """Return a compact catalog description suitable for a model prompt."""

    sections = []
    for template in _TEMPLATES:
        use_when = "; ".join(template.use_when)
        avoid_when = "; ".join(template.avoid_when)
        slots = ", ".join(slot.slot_id for slot in template.assumption_slots)
        sections.append(
            f"- {template.template_id.value} ({template.name_ko}): "
            f"use when {use_when}. Avoid when {avoid_when}. Slots: {slots}."
        )
    return "\n".join(sections)
