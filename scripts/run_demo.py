"""
End-to-end demo driver for ThesisGuard MVP.

Prerequisite: the API must already be running, e.g. from backend/:
    uvicorn app.main:app --reload --port 8000

What this script does, hitting only the public HTTP API (no direct DB/graph
imports), exactly mirroring what the frontend does:

  1. GET  /api/portfolios                      -> find the AVGO holding
  2. POST /api/holdings/{id}/thesis             -> register the natural-language
                                                    AVGO thesis from the proposal,
                                                    print the LLM's structured result
  3. POST /api/theses/{id}/analyze              -> run the full LangGraph pipeline
                                                    against mock AVGO news, print
                                                    confidence change + explanation
"""
import os
import sys
import json

import requests

BASE_URL = os.getenv("THESISGUARD_API", "http://127.0.0.1:8000")

AVGO_RAW_THESIS = (
    "Broadcom은 AI 데이터센터 네트워크와 Custom ASIC 시장에서 성장할 것이며, "
    "Hyperscaler가 자체 AI Chip을 개발할수록 수혜를 받을 가능성이 높다."
)


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    _section("STEP 1. GET /api/portfolios - locate AVGO holding")
    resp = requests.get(f"{BASE_URL}/api/portfolios")
    resp.raise_for_status()
    portfolios = resp.json()

    avgo_holding = None
    for portfolio in portfolios:
        for holding in portfolio["holdings"]:
            if holding["ticker"] == "AVGO":
                avgo_holding = holding
                break
    if avgo_holding is None:
        print("AVGO holding not found - did the API seed correctly?", file=sys.stderr)
        sys.exit(1)

    print(f"Found AVGO holding id={avgo_holding['id']} (has_thesis={avgo_holding['has_thesis']})")

    if avgo_holding["has_thesis"]:
        print("AVGO already has a thesis registered - fetching it instead of re-creating.")
        resp = requests.get(f"{BASE_URL}/api/holdings/{avgo_holding['id']}/thesis")
        resp.raise_for_status()
        thesis = resp.json()
    else:
        _section("STEP 2. POST /api/holdings/{id}/thesis - structure natural-language thesis (REAL LLM CALL)")
        print(f"Raw input:\n  \"{AVGO_RAW_THESIS}\"\n")
        resp = requests.post(
            f"{BASE_URL}/api/holdings/{avgo_holding['id']}/thesis",
            json={"raw_text": AVGO_RAW_THESIS},
        )
        resp.raise_for_status()
        thesis = resp.json()

        print("Structured thesis:")
        print(f"  Main Thesis   : {thesis['main_thesis']}")
        print("  Key Premises  :")
        for p in thesis["key_premises"]:
            print(f"    - {p}")
        print("  Risks         :")
        for r in thesis["risks"]:
            print(f"    - {r}")

    _section("STEP 3. POST /api/theses/{id}/analyze - run full LangGraph pipeline (REAL LLM CALLS)")
    print("Research -> Evidence Extraction -> Evidence Classification -> Bull -> Bear -> Judge\n")
    resp = requests.post(f"{BASE_URL}/api/theses/{thesis['id']}/analyze")
    resp.raise_for_status()
    result = resp.json()

    print(f"Ticker: {result['ticker']}")
    print(f"Confidence: {result['previous_confidence']} -> {result['new_confidence']}")
    print(f"Status: {result['previous_status']} -> {result['new_status']}")

    print("\n--- Evidence classification ---")
    for ev in result["evidence"]:
        print(f"  [{ev['source_id']}] {ev['classification']} (impact={ev['impact']})")
        print(f"    related premise: {ev['related_premise']}")
        print(f"    reasoning: {ev['reasoning']}")

    print("\n--- Bull Agent ---")
    print(f"  {result['bull_argument']}")

    print("\n--- Bear Agent ---")
    print(f"  {result['bear_argument']}")

    print("\n--- Judge verdict (explainable alert) ---")
    print(f"  what_changed        : {result['what_changed']}")
    print(f"  conflicting_premises: {result['conflicting_premises']}")
    print(f"  overall_judgment    : {result['overall_judgment']}")
    print(f"  watch_points        : {result['watch_points']}")

    _section("DONE - full pipeline ran end-to-end")


if __name__ == "__main__":
    main()
