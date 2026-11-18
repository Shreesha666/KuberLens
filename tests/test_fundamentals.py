"""
Unit tests for Fundamental Analysis & Multi-Factor Scoring Engine.
Tests valuation, profitability, solvency, growth, and ownership scores,
along with sector-relative evaluations and dynamic driver generation.
"""
import pytest

from apps.instruments.models import Instrument
from services.fundamentals.analyzer import FundamentalAnalyzer


@pytest.fixture
def sample_instrument(db):
    inst = Instrument.objects.create(
        isin="INE002A01018",
        legal_name="Reliance Industries Limited",
        display_name="Reliance",
        sector="Energy",
        industry="Refineries",
        market_cap_category="LARGE",
    )
    return inst


@pytest.mark.django_db
class TestFundamentalAnalyzer:
    def test_strong_fundamentals_high_score(self, sample_instrument):
        data = {
            "pe_ratio": 18.0,
            "sector_pe": 25.0,  # Discounted P/E
            "pb_ratio": 2.5,
            "dividend_yield": 2.8,
            "roe": 22.5,         # Excellent ROE
            "roce": 24.0,        # Excellent ROCE
            "operating_margin": 20.0,
            "debt_to_equity": 0.20,  # Minimal debt
            "current_ratio": 2.1,
            "revenue_growth_yoy": 18.0,
            "profit_growth_yoy": 22.0,
            "promoter_holding": 52.0,
            "fii_holding": 25.0,
            "dii_holding": 15.0,
        }

        snapshot = FundamentalAnalyzer.evaluate_instrument(sample_instrument, data)
        assert snapshot.overall_score >= 75
        assert snapshot.profitability_score >= 80
        assert snapshot.financial_health_score >= 80
        assert snapshot.valuation_score >= 70
        assert snapshot.piotroski_f_score >= 6
        assert snapshot.altman_z_score is not None and snapshot.altman_z_score > 2.5

        # Positive drivers compiled
        assert len(snapshot.positive_factors) >= 3
        assert any("debt-free" in str(p).lower() or "debt" in str(p).lower() for p in snapshot.positive_factors)
        assert any("return on equity" in str(p).lower() for p in snapshot.positive_factors)

    def test_distressed_fundamentals_low_score(self, sample_instrument):
        data = {
            "pe_ratio": 45.0,
            "sector_pe": 20.0,  # Heavy valuation premium
            "roe": 4.5,          # Weak ROE
            "debt_to_equity": 2.2,  # Over-leveraged
            "current_ratio": 0.8,   # Weak liquidity
            "revenue_growth_yoy": 2.0,
            "profit_growth_yoy": -12.0,  # Negative earnings growth
            "promoter_holding": 22.0,    # Low promoter commitment
        }

        snapshot = FundamentalAnalyzer.evaluate_instrument(sample_instrument, data)
        assert snapshot.overall_score <= 40
        assert snapshot.financial_health_score <= 30
        assert snapshot.growth_score <= 30
        assert snapshot.piotroski_f_score <= 3

        # Risk factors compiled
        assert len(snapshot.negative_factors) >= 2
        assert any("leverage" in str(n).lower() or "debt" in str(n).lower() for n in snapshot.negative_factors)
        assert any("negative" in str(n).lower() or "contracting" in str(n).lower() for n in snapshot.negative_factors)

    def test_missing_data_tracking(self, sample_instrument):
        # Empty/sparse dictionary
        data = {"pe_ratio": 20.0}
        snapshot = FundamentalAnalyzer.evaluate_instrument(sample_instrument, data)
        assert "roe" in snapshot.missing_fields
        assert "debt_to_equity" in snapshot.missing_fields
        assert snapshot.calculation_version == "fund-v2.0.0"
