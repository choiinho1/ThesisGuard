"""
SQLAlchemy ORM models.

Written against plain column types (Integer/String/Float/JSON/DateTime) with no
SQLite-only features, so the same models work unchanged against Postgres by
just swapping DATABASE_URL (see database.py) - e.g. postgresql+psycopg2://...
"""
import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    JSON,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cash_ratio = Column(Float, default=0.0)

    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String, nullable=False)
    quantity = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)
    target_weight = Column(Float, default=0.0)

    portfolio = relationship("Portfolio", back_populates="holdings")
    thesis = relationship("Thesis", back_populates="holding", uselist=False, cascade="all, delete-orphan")


class Thesis(Base):
    __tablename__ = "theses"

    id = Column(Integer, primary_key=True, index=True)
    holding_id = Column(Integer, ForeignKey("holdings.id"), nullable=False, unique=True)
    raw_text = Column(Text, nullable=False)
    main_thesis = Column(Text, nullable=False)
    key_premises = Column(JSON, default=list)  # list[str]
    risks = Column(JSON, default=list)  # list[str]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    holding = relationship("Holding", back_populates="thesis")
    versions = relationship(
        "ThesisVersion", back_populates="thesis", cascade="all, delete-orphan",
        order_by="ThesisVersion.timestamp",
    )
    evidence = relationship(
        "Evidence", back_populates="thesis", cascade="all, delete-orphan",
        order_by="Evidence.created_at",
    )


class ThesisVersion(Base):
    __tablename__ = "thesis_versions"

    id = Column(Integer, primary_key=True, index=True)
    thesis_id = Column(Integer, ForeignKey("theses.id"), nullable=False)
    confidence_score = Column(Integer, nullable=False)  # 0-100
    status = Column(String, nullable=False)
    # reason: {"what_changed", "conflicting_premises"[], "overall_judgment", "watch_points"[]}
    reason = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    thesis = relationship("Thesis", back_populates="versions")


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    thesis_id = Column(Integer, ForeignKey("theses.id"), nullable=False)
    source_id = Column(String, nullable=True)  # mock news id
    source_text = Column(Text, nullable=False)
    related_premise = Column(Text, nullable=True)
    classification = Column(String, nullable=False)  # SUPPORT/CONTRADICT/NEUTRAL/UNCERTAIN
    impact = Column(String, nullable=False)  # HIGH/MEDIUM/LOW
    reasoning = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    thesis = relationship("Thesis", back_populates="evidence")
