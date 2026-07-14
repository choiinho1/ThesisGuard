"""Live ticker quote lookup, backed by mcp_tools.market (Yahoo Finance)."""

from __future__ import annotations

from re import fullmatch

from fastapi import APIRouter, HTTPException, status

from thesisguard_backend import agent_adapters
from thesisguard_backend.deps import CurrentUser
from thesisguard_backend.schemas import MarketQuoteResponse

router = APIRouter(tags=["market"])


@router.get("/api/market/{ticker}/quote", response_model=MarketQuoteResponse)
async def get_market_quote(ticker: str, current_user: CurrentUser) -> MarketQuoteResponse:
    normalized = ticker.strip().upper()
    if fullmatch(r"[A-Z0-9][A-Z0-9.-]*", normalized) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "티커 형식이 올바르지 않습니다.")

    market_data = await agent_adapters.get_market_snapshot(normalized)
    if market_data.latest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{normalized}의 시세를 찾을 수 없습니다.")

    latest = market_data.latest
    return MarketQuoteResponse(
        ticker=market_data.ticker,
        as_of=latest.date,
        price=latest.close,
        day_high=latest.high,
        day_low=latest.low,
        volume=latest.volume,
        change_pct_30d=market_data.change_pct_30d,
    )
