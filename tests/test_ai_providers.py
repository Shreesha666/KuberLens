"""
Unit tests for AI Providers and Abstraction Layer.
"""
from integrations.ai_providers.factory import get_ai_provider
from integrations.ai_providers.fallback import StructuredRuleFallbackProvider
from integrations.ai_providers.gemini import GeminiAIProvider


def test_structured_rule_fallback_provider_investor():
    provider = StructuredRuleFallbackProvider()
    context = {
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Limited",
        "quote": {"current_price": 4000.0, "freshness": "FRESH"},
        "technicals": {
            "sma_20": 3950.0,
            "sma_50": 3900.0,
            "sma_200": 3800.0,
            "rsi_14": 55.0,
            "trend_signal": "BULLISH",
        },
        "fundamentals": {
            "overall_score": 85,
            "pe_ratio": 28.5,
            "sector_pe": 30.0,
            "roe": 45.0,
            "debt_to_equity": 0.05,
        },
        "holdings": {},
        "missing_information": ["Promoter pledge percentage unverified"],
    }

    dto = provider.generate_analysis(prompt="Investor review", structured_context=context, role="INVESTOR")

    assert dto.stock_symbol == "TCS"
    assert dto.overall_view == "BUY_CANDIDATE"
    assert dto.confidence_level == "HIGH"
    assert dto.analysis_horizon == "LONG_TERM"
    assert len(dto.positive_factors) >= 1
    assert any("200-day SMA" in f for f in dto.positive_factors)
    assert any("ROE" in f for f in dto.positive_factors)
    assert "Tata Consultancy Services" in dto.summary
    assert "missing_information" in dir(dto)
    assert "Promoter pledge percentage unverified" in dto.missing_information


def test_structured_rule_fallback_provider_swing_trader():
    provider = StructuredRuleFallbackProvider()
    context = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Limited",
        "quote": {"current_price": 2800.0, "freshness": "FRESH"},
        "technicals": {
            "sma_20": 2750.0,
            "sma_50": 2700.0,
            "rsi_14": 52.0,
            "atr_14": 40.0,
            "trend_signal": "BULLISH",
        },
        "fundamentals": {"overall_score": 75},
        "holdings": {},
        "missing_information": [],
    }

    dto = provider.generate_analysis(prompt="Swing review", structured_context=context, role="SWING_TRADER")

    assert dto.stock_symbol == "RELIANCE"
    assert dto.analysis_horizon == "SWING_TERM"
    assert dto.overall_view == "BUY_CANDIDATE"
    assert "stop-loss" in dto.risk_assessment.lower()
    assert "target" in dto.risk_assessment.lower()


def test_structured_rule_fallback_provider_risk_manager_high_concentration():
    provider = StructuredRuleFallbackProvider()
    context = {
        "symbol": "INFY",
        "company_name": "Infosys Limited",
        "quote": {"current_price": 1800.0},
        "technicals": {},
        "fundamentals": {},
        "holdings": {
            "quantity": 500,
            "portfolio_weight_pct": 22.5,
            "unrealized_pnl_pct": 8.0,
        },
        "missing_information": [],
    }

    dto = provider.generate_analysis(prompt="Risk review", structured_context=context, role="RISK_MANAGER")

    assert dto.stock_symbol == "INFY"
    assert dto.analysis_horizon == "PORTFOLIO_RISK"
    assert dto.overall_view == "REDUCE"
    assert "concentration alert" in dto.summary.lower()


def test_gemini_provider_fallback_without_api_key():
    provider = GeminiAIProvider(api_key="", model_name="gemini-2.0-flash")
    context = {
        "symbol": "HDFCBANK",
        "company_name": "HDFC Bank Limited",
        "quote": {"current_price": 1700.0},
        "technicals": {},
        "fundamentals": {"overall_score": 80},
        "missing_information": ["Debt-to-equity ratio unverified"],
    }

    dto = provider.generate_analysis(prompt="Investor review", structured_context=context, role="INVESTOR")

    assert dto.stock_symbol == "HDFCBANK"
    assert dto.overall_view in ["BUY_CANDIDATE", "HOLD", "WATCH"]
    assert "Debt-to-equity ratio unverified" in dto.missing_information


def test_ai_provider_factory():
    fallback_provider = get_ai_provider("fallback")
    assert isinstance(fallback_provider, StructuredRuleFallbackProvider)

    gemini_provider = get_ai_provider("gemini")
    assert isinstance(gemini_provider, GeminiAIProvider)
