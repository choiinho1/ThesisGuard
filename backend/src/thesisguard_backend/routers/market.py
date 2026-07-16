"""Public market ticker quotes — no auth, powers the homepage ticker bar."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from thesisguard_backend.mcp_tools import market
from thesisguard_backend.schemas import TickerQuoteResponse

router = APIRouter(prefix="/api/market", tags=["market"])

# Display symbol -> Yahoo Finance chart API ticker.
_TICKER_BAR_INSTRUMENTS = {
    "코스피": "^KS11",
    "VIX": "^VIX",
    "TNX": "^TNX",
    "BTC-USD": "BTC-USD",
    "ETH-USD": "ETH-USD",
    "GSPC": "^GSPC",
    "나스닥": "^IXIC",
    "USD/KRW": "KRW=X",
}


@router.get("/ticker", response_model=list[TickerQuoteResponse])
async def get_ticker_quotes() -> list[TickerQuoteResponse]:
    quotes = await asyncio.gather(
        *(market.get_quote(ticker) for ticker in _TICKER_BAR_INSTRUMENTS.values())
    )
    return [
        TickerQuoteResponse(
            symbol=symbol, price=quote.price, change_pct=quote.change_pct, as_of=quote.as_of
        )
        for symbol, quote in zip(_TICKER_BAR_INSTRUMENTS, quotes, strict=True)
    ]
