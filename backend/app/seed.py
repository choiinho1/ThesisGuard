"""Seeds one demo portfolio so the API/frontend has something to show on first run.

Deliberately does NOT seed a thesis for any holding - creating the AVGO thesis
via POST /api/holdings/{id}/thesis is itself part of the demo flow
(see scripts/run_demo.py).
"""
from sqlalchemy.orm import Session

from .models import Portfolio

DEMO_HOLDINGS = [
    {"ticker": "NVDA", "quantity": 40, "avg_price": 118.0, "target_weight": 0.20},
    {"ticker": "AVGO", "quantity": 60, "avg_price": 165.0, "target_weight": 0.15},
    {"ticker": "PLTR", "quantity": 300, "avg_price": 28.0, "target_weight": 0.15},
    {"ticker": "GEV", "quantity": 25, "avg_price": 310.0, "target_weight": 0.10},
    {"ticker": "TSMC", "quantity": 45, "avg_price": 175.0, "target_weight": 0.10},
    {"ticker": "GOOGL", "quantity": 60, "avg_price": 165.0, "target_weight": 0.10},
]


def seed_if_empty(db: Session) -> None:
    if db.query(Portfolio).first() is not None:
        return

    from .models import Holding  # local import avoids circulars at module load

    portfolio = Portfolio(name="AI Growth Portfolio", cash_ratio=0.20)
    db.add(portfolio)
    db.flush()  # assign portfolio.id

    for h in DEMO_HOLDINGS:
        db.add(Holding(portfolio_id=portfolio.id, **h))

    db.commit()
