from __future__ import annotations

import pytest
from agents.models import PortfolioAnalysis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from thesisguard_backend import models as orm
from thesisguard_backend.db import Base
from thesisguard_backend.portfolio_analysis import (
    matches_portfolio_snapshot,
    replace_portfolio_analysis_results,
)


@pytest.mark.asyncio
async def test_replacing_portfolio_analysis_clears_stale_and_empty_results() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = orm.User(email="portfolio-agent@example.com", password_hash="hash")
        portfolio = orm.Portfolio(user=user, name="Test")
        session.add(portfolio)
        await session.flush()
        holding_ids = ["holding-1", "holding-2"]
        session.add(
            orm.AnalysisResult(
                portfolio_id=portfolio.id,
                analysis_type=orm.AnalysisType.THESIS_CONCENTRATION,
                concentration_theme="오래된 테마",
                concentration_score=100,
                affected_holdings=["deleted-holding"],
                raw_result={},
            )
        )
        await session.flush()

        analysis = PortfolioAnalysis.model_validate(
            {
                "themes": [
                    {
                        "theme": "AI CAPEX",
                        "concentration_score": 80,
                        "affected_holdings": holding_ids,
                        "shared_assumptions": ["AI 설비투자 증가"],
                    }
                ],
                "common_risks": [{"risk": "CAPEX 축소", "affected_holdings": holding_ids}],
                "has_concentration_risk": True,
                "summary": "AI CAPEX 전제에 집중되어 있습니다.",
            }
        )
        await replace_portfolio_analysis_results(
            session,
            portfolio_id=portfolio.id,
            analysis=analysis,
            portfolio_holding_ids=holding_ids,
        )
        await session.flush()

        rows = list(
            await session.scalars(
                select(orm.AnalysisResult).where(orm.AnalysisResult.portfolio_id == portfolio.id)
            )
        )
        assert {row.analysis_type for row in rows} == {
            orm.AnalysisType.THESIS_CONCENTRATION,
            orm.AnalysisType.COMMON_RISK,
        }
        concentration = next(
            row for row in rows if row.analysis_type == orm.AnalysisType.THESIS_CONCENTRATION
        )
        assert concentration.concentration_theme == "AI CAPEX"
        assert concentration.judge_summary == "AI CAPEX 전제에 집중되어 있습니다."
        assert matches_portfolio_snapshot(concentration, set(holding_ids)) is True
        assert matches_portfolio_snapshot(concentration, {"holding-1"}) is False

        await replace_portfolio_analysis_results(
            session,
            portfolio_id=portfolio.id,
            analysis=PortfolioAnalysis(),
            portfolio_holding_ids=holding_ids,
        )
        await session.flush()

        assert (
            list(
                await session.scalars(
                    select(orm.AnalysisResult).where(
                        orm.AnalysisResult.portfolio_id == portfolio.id
                    )
                )
            )
            == []
        )

    await engine.dispose()
