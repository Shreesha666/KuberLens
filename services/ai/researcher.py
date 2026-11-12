"""
AI Research Service.
Orchestrates structured financial context assembly, missing information detection,
role-specific prompt formatting, and research opinion persistence.
"""
import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.ai_analysis.models import (
    AIOpinionLabel,
    AIRole,
    AnalysisHorizon,
    ConfidenceLevel,
    StockAIAnalysis,
)
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import Holding
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from integrations.ai_providers.factory import get_ai_provider

logger = logging.getLogger(__name__)


class AIResearchService:
    """
    Core domain service that powers Investor AI, Swing Trader AI, and Portfolio Risk Manager.
    """

    @classmethod
    def gather_structured_context(
        cls,
        listing: ExchangeListing,
        user=None,
    ) -> dict[str, Any]:
        """
        Gathers verified structured financial metrics for a listing and audits for missing data.
        """
        inst = listing.instrument
        missing_info: list[str] = []

        # 1. Market Quote & Price Data
        quote = MarketQuote.objects.filter(listing=listing).first()
        quote_data: dict[str, Any] = {}
        if quote:
            quote_data = {
                "current_price": float(quote.price),
                "change": float(quote.change),
                "change_percent": float(quote.change_percent),
                "high": float(quote.high) if quote.high else None,
                "low": float(quote.low) if quote.low else None,
                "volume": quote.volume,
                "freshness": quote.freshness_status,
                "source": quote.source_type,
            }
        else:
            missing_info.append("Live intraday quote unavailable; relying on latest available EOD price.")

        # 2. Technical Indicators
        tech_snap = TechnicalIndicatorSnapshot.objects.filter(listing=listing).first()
        tech_data: dict[str, Any] = {}
        if tech_snap:
            tech_data = {
                "trend_signal": tech_snap.trend_signal,
                "sma_20": float(tech_snap.sma_20) if tech_snap.sma_20 else None,
                "sma_50": float(tech_snap.sma_50) if tech_snap.sma_50 else None,
                "sma_100": float(tech_snap.sma_100) if tech_snap.sma_100 else None,
                "sma_200": float(tech_snap.sma_200) if tech_snap.sma_200 else None,
                "ema_9": float(tech_snap.ema_9) if tech_snap.ema_9 else None,
                "ema_20": float(tech_snap.ema_20) if tech_snap.ema_20 else None,
                "ema_50": float(tech_snap.ema_50) if tech_snap.ema_50 else None,
                "rsi_14": float(tech_snap.rsi_14) if tech_snap.rsi_14 else None,
                "macd": float(tech_snap.macd_line) if tech_snap.macd_line else None,
                "macd_signal": float(tech_snap.macd_signal) if tech_snap.macd_signal else None,
                "bollinger_upper": float(tech_snap.bollinger_upper) if tech_snap.bollinger_upper else None,
                "bollinger_lower": float(tech_snap.bollinger_lower) if tech_snap.bollinger_lower else None,
                "atr_14": float(tech_snap.atr_14) if tech_snap.atr_14 else None,
            }
            if not tech_snap.sma_200:
                missing_info.append("Insufficient trading sessions (requires 200 bars) to calculate 200-day SMA.")
            if not tech_snap.atr_14:
                missing_info.append("14-period Average True Range (ATR) uncalculated; using 2% price baseline.")
        else:
            missing_info.append("Technical indicator snapshot missing for this instrument.")

        # 3. Fundamental Health & Valuation
        fund_snap = FundamentalSnapshot.objects.filter(instrument=inst).first()
        fund_data: dict[str, Any] = {}
        if fund_snap:
            fund_data = {
                "overall_score": fund_snap.overall_score,
                "growth_score": fund_snap.growth_score,
                "profitability_score": fund_snap.profitability_score,
                "financial_health_score": fund_snap.financial_health_score,
                "valuation_score": fund_snap.valuation_score,
                "pe_ratio": float(fund_snap.pe_ratio) if fund_snap.pe_ratio else None,
                "sector_pe": float(fund_snap.sector_pe) if fund_snap.sector_pe else None,
                "pb_ratio": float(fund_snap.pb_ratio) if fund_snap.pb_ratio else None,
                "roe": float(fund_snap.roe) if fund_snap.roe else None,
                "roce": float(fund_snap.roce) if fund_snap.roce else None,
                "debt_to_equity": float(fund_snap.debt_to_equity) if fund_snap.debt_to_equity else None,
            }
            if fund_snap.debt_to_equity is None:
                missing_info.append("Debt-to-equity ratio not disclosed in latest financial statement snapshot.")
            if fund_snap.pe_ratio is None:
                missing_info.append("Price-to-Earnings (P/E) ratio unavailable due to negative or zero TTM EPS.")
        else:
            missing_info.append("Fundamental financial statement snapshot not yet populated.")

        # Always catalog standard unverified institutional attributes
        missing_info.append("Promoter share pledge status and foreign institutional flow breakdown unverified.")

        # 4. User Holdings Context (if user supplied)
        holdings_data: dict[str, Any] = {
            "quantity": 0,
            "invested_value": 0.0,
            "current_value": 0.0,
            "unrealized_pnl_pct": 0.0,
            "portfolio_weight_pct": 0.0,
        }
        if user and user.is_authenticated:
            holding = Holding.objects.filter(portfolio__user=user, listing=listing, total_quantity__gt=0).first()
            if holding:
                all_holdings = Holding.objects.filter(portfolio__user=user, total_quantity__gt=0)
                total_portfolio_val = sum(float(h.current_value) for h in all_holdings)
                curr_val = float(holding.current_value) if holding.current_value else float(holding.total_quantity * (quote.price if quote else holding.average_buy_price))
                weight = (curr_val / total_portfolio_val * 100) if total_portfolio_val > 0 else 0.0

                holdings_data = {
                    "quantity": holding.total_quantity,
                    "invested_value": float(holding.invested_amount),
                    "current_value": curr_val,
                    "unrealized_pnl_pct": float(holding.unrealised_pnl_percent),
                    "portfolio_weight_pct": round(weight, 2),
                }

        return {
            "symbol": listing.symbol,
            "company_name": inst.legal_name or inst.display_name,
            "isin": inst.isin,
            "sector": inst.sector,
            "market_cap_category": inst.market_cap_category,
            "quote": quote_data,
            "technicals": tech_data,
            "fundamentals": fund_data,
            "holdings": holdings_data,
            "missing_information": missing_info,
        }

    @classmethod
    def get_prompt_for_role(cls, role: str) -> str:
        """
        Returns structured system prompt instructions tailored to the chosen persona.
        """
        if role == AIRole.INVESTOR:
            return (
                "You are Investor AI. Conduct thorough long-term equity research for an investment horizon of 1 to 3 years. "
                "Evaluate business franchise durability, balance sheet health, return on equity, and valuation multiples relative to sector. "
                "Categorize the overall view strictly into BUY CANDIDATE, HOLD, WATCH, AVOID, REDUCE, or EXIT."
            )
        elif role == AIRole.SWING_TRADER:
            return (
                "You are Swing Trader AI. Conduct structured quantitative swing trading research for a horizon of 1 to 4 weeks. "
                "Analyze moving average trend alignment, 14-period RSI momentum, volatility ATR, support/resistance breakout levels. "
                "Provide precise entry zones, stop losses, and target prices with at least 1:1.5 Risk-to-Reward ratio."
            )
        else:  # RISK_MANAGER
            return (
                "You are Portfolio Risk Manager AI. Focus on capital preservation, concentration exposure, and downside drawdowns. "
                "Audit user holdings, warn if single-stock weight exceeds 15%, and recommend appropriate hold, trim, reduce, or exit actions."
            )

    @classmethod
    def analyze_stock(
        cls,
        listing: ExchangeListing,
        role: str = AIRole.INVESTOR,
        user=None,
        force_refresh: bool = False,
    ) -> StockAIAnalysis:
        """
        Analyzes a stock using the configured AI Provider and persists the structured brief.
        Reuses recent analyses within 4 hours unless force_refresh=True.
        """
        # Check cache if not force_refresh
        cache_cutoff = timezone.now() - timedelta(hours=4)
        existing = StockAIAnalysis.objects.filter(
            listing=listing,
            role=role,
            created_at__gte=cache_cutoff,
        ).first()

        if existing and not force_refresh:
            return existing

        structured_context = cls.gather_structured_context(listing, user=user)
        prompt = cls.get_prompt_for_role(role)

        provider = get_ai_provider()
        dto = provider.generate_analysis(prompt, structured_context, role)

        # Normalize overall view label
        overall_view = dto.overall_view.upper().replace(" ", "_")
        if overall_view not in AIOpinionLabel.values:
            overall_view = AIOpinionLabel.WATCH

        # Normalize confidence
        confidence = dto.confidence_level.upper()
        if confidence not in ConfidenceLevel.values:
            confidence = ConfidenceLevel.MEDIUM

        # Normalize horizon
        horizon = dto.analysis_horizon.upper()
        if horizon not in AnalysisHorizon.values:
            horizon = AnalysisHorizon.LONG_TERM if role == AIRole.INVESTOR else AnalysisHorizon.SWING_TERM

        analysis = StockAIAnalysis.objects.create(
            listing=listing,
            user=user if (user and user.is_authenticated) else None,
            role=role,
            overall_view=overall_view,
            confidence_level=confidence,
            analysis_horizon=horizon,
            summary=dto.summary,
            positive_factors=dto.positive_factors,
            negative_factors=dto.negative_factors,
            technical_analysis=dto.technical_analysis,
            fundamental_analysis=dto.fundamental_analysis,
            risk_assessment=dto.risk_assessment,
            existing_holder_view=dto.existing_holder_view,
            new_investor_view=dto.new_investor_view,
            entry_conditions=dto.entry_conditions,
            invalidation_conditions=dto.invalidation_conditions,
            missing_information=dto.missing_information,
            data_sources_and_assumptions=dto.data_sources_and_assumptions,
            data_freshness=dto.data_freshness,
            prompt_version=dto.prompt_version,
            model_name=dto.model_name,
            raw_response=dto.raw_response,
        )

        return analysis
