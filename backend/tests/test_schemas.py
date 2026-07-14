import pytest
from pydantic import ValidationError

from thesisguard_backend.schemas import (
    HoldingCreateRequest,
    PortfolioCreateRequest,
    SignupRequest,
    ThesisCreateRequest,
)


def test_signup_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(email="user@example.com", password="short")


def test_signup_accepts_valid_payload() -> None:
    request = SignupRequest(email="user@example.com", password="longenoughpassword", name="Kim")
    assert request.email == "user@example.com"


def test_portfolio_cash_ratio_bounds() -> None:
    with pytest.raises(ValidationError):
        PortfolioCreateRequest(name="AI Growth", cash_ratio=150)
    ok = PortfolioCreateRequest(name="AI Growth", cash_ratio=20)
    assert ok.cash_ratio == 20


def test_thesis_raw_input_minimum_length() -> None:
    with pytest.raises(ValidationError):
        ThesisCreateRequest(raw_input="too short")
    ok = ThesisCreateRequest(raw_input="NVDA is well positioned for continued AI capex growth.")
    assert "NVDA" in ok.raw_input


def test_holding_ticker_is_normalized() -> None:
    request = HoldingCreateRequest(ticker=" crdo ", quantity=1, avg_buy_price=10, target_weight=5)

    assert request.ticker == "CRDO"
