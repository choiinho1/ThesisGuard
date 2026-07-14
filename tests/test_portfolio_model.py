from __future__ import annotations

from agents.model import LangChainAnalysisModel
from agents.models import PortfolioAnalysis, PortfolioThesis, StructuredThesis


def _portfolio_thesis(holding_id: str, ticker: str, weight: float) -> PortfolioThesis:
    return PortfolioThesis(
        holding_id=holding_id,
        ticker=ticker,
        current_weight=weight,
        thesis=StructuredThesis(
            raw_input=f"{ticker}의 데이터센터 수요가 장기간 증가할 것이다.",
            main_thesis=f"{ticker} 데이터센터 성장",
            key_assumptions=["데이터센터 설비투자 증가"],
        ),
    )


async def test_portfolio_analysis_rejects_absence_placeholders_and_deduplicates_ids(
    monkeypatch,
) -> None:
    model = LangChainAnalysisModel(object())  # type: ignore[arg-type]
    model_output = PortfolioAnalysis.model_validate(
        {
            "themes": [
                {
                    "theme": "공통된 테마가 없음",
                    "concentration_score": 100,
                    "affected_holdings": ["holding-1", "holding-2"],
                    "shared_assumptions": [],
                },
                {
                    "theme": "AI 데이터센터 투자",
                    "concentration_score": 1,
                    "affected_holdings": ["holding-1", "holding-1", "holding-2", "unknown"],
                    "shared_assumptions": ["데이터센터 설비투자 증가", "데이터센터 설비투자 증가"],
                },
            ],
            "common_risks": [
                {
                    "risk": "공통 위험 없음",
                    "affected_holdings": ["holding-1", "holding-2"],
                },
                {
                    "risk": "고객 설비투자 축소",
                    "affected_holdings": ["holding-1", "holding-1", "holding-2"],
                    "evidence_document_ids": ["untrusted-document-id"],
                },
            ],
            "has_concentration_risk": True,
            "summary": "AI 데이터센터 투자 전제에 집중되어 있습니다.",
        }
    )

    async def fake_invoke(_schema, _task):
        return model_output

    monkeypatch.setattr(model, "_invoke", fake_invoke)
    portfolio = [
        _portfolio_thesis("holding-1", "NVDA", 55),
        _portfolio_thesis("holding-2", "MU", 25),
        _portfolio_thesis("holding-3", "SGOV", 20),
    ]

    result = await model.analyze_portfolio(portfolio)

    assert [theme.theme for theme in result.themes] == ["AI 데이터센터 투자"]
    assert result.themes[0].affected_holdings == ["holding-1", "holding-2"]
    assert result.themes[0].shared_assumptions == ["데이터센터 설비투자 증가"]
    assert result.themes[0].concentration_score == 80
    assert [risk.risk for risk in result.common_risks] == ["고객 설비투자 축소"]
    assert result.common_risks[0].affected_holdings == ["holding-1", "holding-2"]
    assert result.common_risks[0].evidence_document_ids == []
    assert result.has_concentration_risk is True


async def test_portfolio_analysis_returns_empty_result_for_fewer_than_two_theses() -> None:
    model = LangChainAnalysisModel(object())  # type: ignore[arg-type]

    result = await model.analyze_portfolio([_portfolio_thesis("holding-1", "NVDA", 100)])

    assert result.themes == []
    assert result.common_risks == []
    assert result.has_concentration_risk is False
    assert result.summary == "집중 테마 없음"
