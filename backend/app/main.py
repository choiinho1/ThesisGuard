"""
ThesisGuard MVP API.

Run with:  uvicorn app.main:app --reload --port 8000   (from backend/)

Endpoints
---------
GET  /api/portfolios                      list portfolios + holdings + latest thesis confidence/status
GET  /api/holdings/{holding_id}/thesis     get the structured thesis (+ version history + evidence) for a holding
POST /api/holdings/{holding_id}/thesis     register a natural-language thesis -> LLM structures it (real call)
POST /api/theses/{thesis_id}/analyze      run the full LangGraph pipeline against mock news (real LLM calls)
"""
import datetime

from dotenv import load_dotenv

load_dotenv()  # picks up ANTHROPIC_API_KEY / ANTHROPIC_MODEL / DATABASE_URL from .env if present

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db, SessionLocal
from .seed import seed_if_empty
from .workflow.node_thesis_structuring import structure_thesis
from .workflow.node_portfolio_recommendation import recommend_portfolio
from .workflow.node_thesis_reality_snapshot import snapshot_thesis_reality
from .workflow.graph import analysis_graph

app = FastAPI(title="ThesisGuard MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


def _latest_version(thesis: models.Thesis | None) -> models.ThesisVersion | None:
    if thesis is None or not thesis.versions:
        return None
    return thesis.versions[-1]


@app.get("/api/portfolios", response_model=list[schemas.PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)):
    portfolios = db.query(models.Portfolio).all()
    out = []
    for p in portfolios:
        holdings_out = []
        for h in p.holdings:
            latest = _latest_version(h.thesis)
            holdings_out.append(
                schemas.HoldingOut(
                    id=h.id,
                    ticker=h.ticker,
                    quantity=h.quantity,
                    avg_price=h.avg_price,
                    target_weight=h.target_weight,
                    latest_confidence=latest.confidence_score if latest else None,
                    latest_status=latest.status if latest else None,
                    has_thesis=h.thesis is not None,
                )
            )
        out.append(
            schemas.PortfolioOut(id=p.id, name=p.name, cash_ratio=p.cash_ratio, holdings=holdings_out)
        )
    return out


@app.get("/api/holdings/{holding_id}/thesis", response_model=schemas.ThesisOut)
def get_thesis_by_holding(holding_id: int, db: Session = Depends(get_db)):
    holding = db.get(models.Holding, holding_id)
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.thesis is None:
        raise HTTPException(status_code=404, detail="No thesis registered for this holding yet")
    return holding.thesis


@app.post("/api/holdings/{holding_id}/thesis", response_model=schemas.ThesisOut)
def create_thesis(holding_id: int, body: schemas.ThesisCreateIn, db: Session = Depends(get_db)):
    holding = db.get(models.Holding, holding_id)
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.thesis is not None:
        raise HTTPException(status_code=400, detail="Holding already has a thesis registered")

    structured = structure_thesis(holding.ticker, body.raw_text)

    thesis = models.Thesis(
        holding_id=holding.id,
        raw_text=body.raw_text,
        main_thesis=structured["main_thesis"],
        key_premises=structured["key_premises"],
        risks=structured["risks"],
    )
    db.add(thesis)
    db.flush()

    db.add(
        models.ThesisVersion(
            thesis_id=thesis.id,
            confidence_score=75,
            status="UNCHANGED",
            reason={
                "what_changed": "초기 등록",
                "conflicting_premises": [],
                "overall_judgment": "사용자가 최초 등록한 투자 논리이며, 아직 신규 증거로 검증되지 않았습니다.",
                "watch_points": [],
            },
        )
    )
    db.commit()
    db.refresh(thesis)
    return thesis


@app.get("/api/theses/{thesis_id}", response_model=schemas.ThesisOut)
def get_thesis(thesis_id: int, db: Session = Depends(get_db)):
    thesis = db.get(models.Thesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")
    return thesis


@app.post("/api/theses/{thesis_id}/analyze", response_model=schemas.AnalyzeResultOut)
def analyze_thesis(thesis_id: int, db: Session = Depends(get_db)):
    thesis = db.get(models.Thesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Thesis not found")

    latest = _latest_version(thesis)
    previous_confidence = latest.confidence_score if latest else 75
    previous_status = latest.status if latest else "UNCHANGED"

    initial_state = {
        "ticker": thesis.holding.ticker,
        "main_thesis": thesis.main_thesis,
        "key_premises": thesis.key_premises,
        "risks": thesis.risks,
        "previous_confidence": previous_confidence,
        "previous_status": previous_status,
    }

    result_state = analysis_graph.invoke(initial_state)
    judge = result_state["judge_result"]

    db.add(
        models.ThesisVersion(
            thesis_id=thesis.id,
            confidence_score=judge["new_confidence_score"],
            status=judge["status"],
            reason={
                "what_changed": judge["what_changed"],
                "conflicting_premises": judge["conflicting_premises"],
                "overall_judgment": judge["overall_judgment"],
                "watch_points": judge["watch_points"],
            },
            timestamp=datetime.datetime.utcnow(),
        )
    )

    new_evidence_rows = []
    for ev in result_state["classified_evidence"]:
        row = models.Evidence(
            thesis_id=thesis.id,
            source_id=ev["news_id"],
            source_text=ev["source_text"],
            related_premise=ev["related_premise"],
            classification=ev["classification"],
            impact=ev["impact"],
            reasoning=ev["reasoning"],
        )
        db.add(row)
        new_evidence_rows.append(row)

    db.commit()
    for row in new_evidence_rows:
        db.refresh(row)

    return schemas.AnalyzeResultOut(
        ticker=thesis.holding.ticker,
        previous_confidence=previous_confidence,
        new_confidence=judge["new_confidence_score"],
        previous_status=previous_status,
        new_status=judge["status"],
        what_changed=judge["what_changed"],
        conflicting_premises=judge["conflicting_premises"],
        overall_judgment=judge["overall_judgment"],
        watch_points=judge["watch_points"],
        bull_argument=result_state["bull_result"]["argument"],
        bear_argument=result_state["bear_result"]["argument"],
        evidence=new_evidence_rows,
    )


@app.post("/api/recommendations", response_model=schemas.RecommendationOut)
def create_recommendation(body: schemas.RecommendationIn, db: Session = Depends(get_db)):
    """Turn a free-text goal into a recommended portfolio (REAL LLM CALL), and
    immediately save it as a new Portfolio so it shows up on the dashboard.
    quantity/avg_price are left at 0 since this is a draft, not an actual
    fill - the user is expected to edit those once they act on it.
    """
    result = recommend_portfolio(body.goal_text)

    portfolio = models.Portfolio(
        name=f"AI 추천 포트폴리오 - {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        cash_ratio=result["cash_ratio"],
    )
    db.add(portfolio)
    db.flush()

    for h in result["holdings"]:
        db.add(
            models.Holding(
                portfolio_id=portfolio.id,
                ticker=h["ticker"],
                quantity=0,
                avg_price=0,
                target_weight=h["weight"],
            )
        )
    db.commit()

    return schemas.RecommendationOut(
        portfolio_id=portfolio.id,
        strategy_summary=result["strategy_summary"],
        holdings=[schemas.RecommendationHoldingOut(**h) for h in result["holdings"]],
        cash_ratio=result["cash_ratio"],
        knowledge_cutoff_caveat=result["knowledge_cutoff_caveat"],
    )


@app.post("/api/portfolio-check", response_model=schemas.PortfolioCheckOut)
def check_portfolio(body: schemas.PortfolioCheckIn):
    """Accepts an arbitrary list of {ticker, weight} - the user's own draft,
    or someone else's portfolio they copied in - with NO thesis text
    required and NO DB persistence. For each holding, infers a plausible
    thesis and immediately judges whether it still looks valid today, using
    only the model's own knowledge (see node_thesis_reality_snapshot.py for
    the caveats this carries). Stateless by design: re-run any time to get a
    fresh read, nothing is saved.
    """
    results = []
    for h in body.holdings:
        snapshot = snapshot_thesis_reality(h.ticker, weight=h.weight)
        results.append(
            schemas.PortfolioCheckHoldingOut(
                ticker=h.ticker,
                weight=h.weight,
                main_thesis=snapshot["main_thesis"],
                key_premises=snapshot["key_premises"],
                risks=snapshot["risks"],
                reality_status=snapshot["reality_status"],
                confidence_score=snapshot["confidence_score"],
                reasoning=snapshot["reasoning"],
                caveats=snapshot["caveats"],
            )
        )

    return schemas.PortfolioCheckOut(label=body.label, holdings=results)
