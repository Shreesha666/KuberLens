"""
Fundamental Analysis & Multi-Factor Scoring Engine.
Computes multi-factor scores, evaluates sector-relative valuations, and compiles qualitative drivers.
"""
import logging
from decimal import Decimal

from django.utils import timezone

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import Instrument

logger = logging.getLogger(__name__)


class FundamentalAnalyzer:
    CALCULATION_VERSION = "fund-v2.0.0"

    @classmethod
    def evaluate_instrument(
        cls,
        instrument: Instrument,
        raw_data: dict,
        calculation_version: str | None = None,
    ) -> FundamentalSnapshot:
        """
        Evaluates corporate fundamental inputs, derives 5-factor component scores,
        compiles strengths and risk factors, and persists the snapshot.
        """
        version = calculation_version or cls.CALCULATION_VERSION
        positives = []
        negatives = []
        missing = []

        def get_dec(field: str):
            val = raw_data.get(field)
            if val is None or str(val).strip() == "":
                missing.append(field)
                return None
            return Decimal(str(val))

        # 1. Ratios extraction
        pe = get_dec("pe_ratio")
        pb = get_dec("pb_ratio")
        ps = get_dec("ps_ratio")
        ev_ebitda = get_dec("ev_to_ebitda")
        div_yield = get_dec("dividend_yield")
        div_rate = get_dec("dividend_rate")
        sector_pe = get_dec("sector_pe") or Decimal("25.0")

        roe = get_dec("roe")
        roce = get_dec("roce")
        op_margin = get_dec("operating_margin")
        net_margin = get_dec("net_profit_margin")
        eps = get_dec("eps")

        de = get_dec("debt_to_equity")
        current_ratio = get_dec("current_ratio")
        interest_cov = get_dec("interest_coverage_ratio")
        fcf = get_dec("free_cash_flow")

        rev_growth = get_dec("revenue_growth_yoy")
        profit_growth = get_dec("profit_growth_yoy")

        promoter = get_dec("promoter_holding")
        fii = get_dec("fii_holding")
        dii = get_dec("dii_holding")
        public = get_dec("public_holding")

        # 2. Valuation Score (0 to 100)
        val_score = 50
        if pe is not None and sector_pe is not None:
            if pe < sector_pe * Decimal("0.8"):
                val_score += 25
                positives.append(f"Attractive valuation: P/E ({pe}) is discounted relative to sector average ({sector_pe}).")
            elif pe > sector_pe * Decimal("1.3"):
                val_score -= 20
                negatives.append(f"Premium valuation: P/E ({pe}) trades significantly above sector benchmark ({sector_pe}).")

        if pb is not None:
            if pb < Decimal("2.0"):
                val_score += 10
            elif pb > Decimal("8.0"):
                val_score -= 10

        if div_yield is not None and div_yield > Decimal("2.5"):
            val_score += 15
            positives.append(f"Solid dividend yield of {div_yield}% provides downside cushion.")

        val_score = max(10, min(95, val_score))

        # 3. Profitability Score (0 to 100)
        prof_score = 50
        if roe is not None:
            if roe >= Decimal("20.0"):
                prof_score += 25
                positives.append(f"Outstanding Return on Equity (ROE: {roe}%).")
            elif roe >= Decimal("14.0"):
                prof_score += 15
            elif roe < Decimal("8.0"):
                prof_score -= 25
                negatives.append(f"Subdued capital productivity: ROE ({roe}%) below corporate cost of capital.")

        if roce is not None and roce >= Decimal("18.0"):
            prof_score += 15
            positives.append(f"Superior Return on Capital Employed (ROCE: {roce}%).")

        if op_margin is not None and op_margin >= Decimal("18.0"):
            prof_score += 10

        prof_score = max(10, min(95, prof_score))

        # 4. Financial Health Score (0 to 100)
        health_score = 50
        if de is not None:
            if de <= Decimal("0.3"):
                health_score += 30
                positives.append(f"Virtually debt-free balance sheet: Debt-to-Equity is {de}.")
            elif de <= Decimal("0.8"):
                health_score += 15
            elif de > Decimal("1.5"):
                health_score -= 30
                negatives.append(f"Elevated financial leverage: Debt-to-Equity ({de}) poses solvency risk.")

        if current_ratio is not None:
            if current_ratio >= Decimal("1.33"):
                health_score += 10
            elif current_ratio < Decimal("1.0"):
                health_score -= 15
                negatives.append(f"Weak liquidity: Current ratio ({current_ratio}) is below 1.0.")

        health_score = max(10, min(95, health_score))

        # 5. Growth Score (0 to 100)
        growth_score = 50
        if rev_growth is not None:
            if rev_growth >= Decimal("15.0"):
                growth_score += 25
                positives.append(f"Strong topline expansion: Revenue YoY growth is {rev_growth}%.")
            elif rev_growth < Decimal("5.0"):
                growth_score -= 15

        if profit_growth is not None:
            if profit_growth >= Decimal("20.0"):
                growth_score += 25
                positives.append(f"Robust net profit acceleration: Profit YoY growth of {profit_growth}%.")
            elif profit_growth < Decimal("0.0"):
                growth_score -= 25
                negatives.append(f"Contracting earnings: Net profit growth is negative ({profit_growth}%).")

        growth_score = max(10, min(95, growth_score))

        # 6. Ownership Score (0 to 100)
        owner_score = 50
        if promoter is not None:
            if promoter >= Decimal("50.0"):
                owner_score += 20
                positives.append(f"High promoter commitment ({promoter}% shareholding).")
            elif promoter < Decimal("30.0"):
                owner_score -= 15

        inst_total = (fii or Decimal("0")) + (dii or Decimal("0"))
        if inst_total >= Decimal("30.0"):
            owner_score += 25
            positives.append(f"Substantial institutional sponsorship (FII + DII holding: {inst_total}%).")

        owner_score = max(10, min(95, owner_score))

        # 7. Institutional Quantitative Metrics (Piotroski F-Score & Altman Z-Score)
        # Piotroski 9-Criteria Scoring (0 to 9)
        f_score = 0
        if net_margin is not None and net_margin > 0:
            f_score += 1
        if roe is not None and roe > 0:
            f_score += 1
        if roce is not None and roce > 0:
            f_score += 1
        if fcf is not None and fcf > 0:
            f_score += 1
        if de is not None and de <= Decimal("0.8"):
            f_score += 1
        if current_ratio is not None and current_ratio >= Decimal("1.2"):
            f_score += 1
        if rev_growth is not None and rev_growth > 0:
            f_score += 1
        if profit_growth is not None and profit_growth > 0:
            f_score += 1
        if op_margin is not None and op_margin >= Decimal("12.0"):
            f_score += 1

        if f_score <= 3:
            negatives.append(f"Value Trap Alert: Weak Piotroski F-Score of {f_score}/9 indicates fundamental deterioration.")
        elif f_score >= 7:
            positives.append(f"Pristine Accounting Quality: Piotroski F-Score of {f_score}/9 confirms operational and financial strength.")

        # Altman Z-Score Solvency Estimate
        altman_z = None
        if current_ratio is not None and roe is not None and op_margin is not None:
            cr_factor = float(current_ratio) * 0.7
            roe_factor = float(roe) * 0.08
            margin_factor = float(op_margin) * 0.12
            de_penalty = float(de or Decimal("0.5")) * 0.4
            raw_z = 1.2 + cr_factor + roe_factor + margin_factor - de_penalty
            altman_z = Decimal(str(round(max(0.5, min(8.0, raw_z)), 2)))

            if altman_z < Decimal("1.81"):
                negatives.append(f"Solvency Distress Warning: Altman Z-Score ({altman_z}) falls within the distress vulnerability zone.")
            elif altman_z > Decimal("2.99"):
                positives.append(f"Impregnable Balance Sheet: Altman Z-Score ({altman_z}) sits firmly in the safe zone.")

        # DuPont 3-Stage ROE Breakdown: ROE = Net Margin * Asset Turnover * Equity Multiplier
        equity_multiplier = None
        asset_turnover = None
        if de is not None:
            equity_multiplier = Decimal("1.0") + de
            if roe is not None and net_margin is not None and net_margin > Decimal("0.0"):
                # Asset Turnover = (ROE / 100) / ((Net Margin / 100) * Equity Multiplier)
                roe_dec = roe / Decimal("100.0")
                net_dec = net_margin / Decimal("100.0")
                denom = net_dec * equity_multiplier
                if denom > Decimal("0.0"):
                    asset_turnover = Decimal(str(round(float(roe_dec / denom), 4)))

        # Overall Weighted Score
        overall = int(
            round(
                (prof_score * 0.25)
                + (growth_score * 0.20)
                + (health_score * 0.20)
                + (val_score * 0.20)
                + (owner_score * 0.15)
            )
        )

        snapshot, _ = FundamentalSnapshot.objects.update_or_create(
            instrument=instrument,
            calculation_version=version,
            defaults={
                "pe_ratio": pe,
                "pb_ratio": pb,
                "ps_ratio": ps,
                "ev_to_ebitda": ev_ebitda,
                "dividend_yield": div_yield,
                "dividend_rate": div_rate,
                "sector_pe": sector_pe,
                "roe": roe,
                "roce": roce,
                "operating_margin": op_margin,
                "net_profit_margin": net_margin,
                "eps": eps,
                "debt_to_equity": de,
                "current_ratio": current_ratio,
                "interest_coverage_ratio": interest_cov,
                "free_cash_flow": fcf,
                "revenue_growth_yoy": rev_growth,
                "profit_growth_yoy": profit_growth,
                "promoter_holding": promoter,
                "fii_holding": fii,
                "dii_holding": dii,
                "public_holding": public,
                "piotroski_f_score": f_score,
                "altman_z_score": altman_z,
                "dupont_asset_turnover": asset_turnover,
                "dupont_equity_multiplier": equity_multiplier,
                "overall_score": overall,
                "growth_score": growth_score,
                "profitability_score": prof_score,
                "valuation_score": val_score,
                "financial_health_score": health_score,
                "ownership_score": owner_score,
                "positive_factors": positives,
                "negative_factors": negatives,
                "missing_fields": missing,
                "calculated_at": timezone.now(),
            },
        )
        return snapshot

    @classmethod
    def sync_dividend_from_yahoo(cls, symbol: str, instrument: Instrument) -> tuple[Decimal | None, Decimal | None]:
        """
        Fetches official dividend rate (DPS in ₹) and yield (%) directly from Yahoo Finance.
        Calculates trailing 12-month (TTM) actual cash dividend payouts from dividends history.
        """
        from datetime import timedelta
        import yfinance as yf
        from django.utils import timezone

        try:
            t = yf.Ticker(f"{symbol}.NS")
            info = getattr(t, "info", None) or {}
            rate = info.get("trailingAnnualDividendRate") or info.get("dividendRate")
            yd = info.get("trailingAnnualDividendYield") or info.get("dividendYield")

            # Check actual corporate dividends history for trailing 12 months
            try:
                divs = getattr(t, "dividends", None)
                if divs is not None and not divs.empty:
                    div_tz = getattr(divs.index, "tz", None)
                    now_tz = timezone.now().astimezone(div_tz) if div_tz else timezone.now()
                    cutoff = now_tz - timedelta(days=365)
                    ttm = divs[divs.index >= cutoff]
                    if not ttm.empty:
                        ttm_sum = float(ttm.sum())
                        if ttm_sum > 0:
                            rate = ttm_sum
            except Exception as e:
                logger.debug("Could not calculate TTM dividends history for %s: %s", symbol, e)

            dec_rate = Decimal(str(round(rate, 2))) if rate is not None else None

            # Calculate accurate yield based on real TTM rate and current price
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            if dec_rate and price:
                dec_yield = Decimal(str(round((float(dec_rate) / float(price)) * 100.0, 2)))
            elif yd is not None:
                dec_yield = Decimal(str(round((yd * 100) if yd < 1.0 else yd, 2)))
            else:
                dec_yield = None

            # Update existing or latest FundamentalSnapshot
            if dec_rate is not None or dec_yield is not None:
                f_snap = FundamentalSnapshot.objects.filter(instrument=instrument).order_by("-calculated_at").first()
                if f_snap:
                    updated_fields = []
                    if dec_rate is not None:
                        f_snap.dividend_rate = dec_rate
                        updated_fields.append("dividend_rate")
                    if dec_yield is not None:
                        f_snap.dividend_yield = dec_yield
                        updated_fields.append("dividend_yield")
                    if updated_fields:
                        f_snap.save(update_fields=updated_fields)

            return dec_rate, dec_yield
        except Exception as err:
            logger.warning("Failed to sync dividend from Yahoo Finance for %s: %s", symbol, err)
            return None, None

    @classmethod
    def get_five_year_dividend_history(
        cls, symbol: str, current_price: float | Decimal | None = None
    ) -> tuple[list[dict], dict]:
        """
        Retrieves the complete 5-year corporate dividend history and analytics for a stock listing.
        Includes ex-date, amount, dividend type (Interim/Final/Special), estimated payment date,
        and dividend yield (%) at the time of distribution.
        """
        from datetime import timedelta
        from django.core.cache import cache
        from django.utils import timezone
        import yfinance as yf

        cache_key = f"div_history_5y_{symbol.upper()}"
        cached_data = cache.get(cache_key)
        if cached_data is not None and isinstance(cached_data, dict):
            return cached_data.get("history", []), cached_data.get("summary", {})

        history = []
        summary = {
            "total_5y_payout": Decimal("0.00"),
            "total_5y_count": 0,
            "ttm_payout": Decimal("0.00"),
            "ttm_yield": None,
            "avg_annual_payout": Decimal("0.00"),
            "paying_years": 0,
            "frequency": "—",
            "growth_streak": 0,
        }

        try:
            t = yf.Ticker(f"{symbol}.NS")
            divs = getattr(t, "dividends", None)
            if divs is None or (hasattr(divs, "empty") and divs.empty):
                # Fallback to BSE ticker if NSE has no dividend records
                t_bse = yf.Ticker(f"{symbol}.BO")
                bse_divs = getattr(t_bse, "dividends", None)
                if bse_divs is not None and not bse_divs.empty:
                    t = t_bse
                    divs = bse_divs

            if divs is not None and not divs.empty:
                div_tz = getattr(divs.index, "tz", None)
                now_tz = timezone.now().astimezone(div_tz) if div_tz else timezone.now()
                today_date = now_tz.date()
                cutoff = now_tz - timedelta(days=5 * 365 + 45)  # 5-year window with buffer
                divs_5y = divs[divs.index >= cutoff].sort_index(ascending=False)

                # Fetch historical close prices for yield-at-distribution calculation
                hist = None
                try:
                    hist = t.history(period="5y")
                except Exception:
                    pass

                cur_p_float = float(current_price) if current_price else None

                years_set = set()
                total_5y_payout = Decimal("0.00")
                ttm_cutoff = now_tz - timedelta(days=365)
                ttm_sum = Decimal("0.00")

                for dt, amt in divs_5y.items():
                    amt_float = float(amt)
                    amt_dec = Decimal(str(round(amt_float, 2)))
                    dt_date = dt.date()
                    years_set.add(dt_date.year)
                    total_5y_payout += amt_dec

                    if dt >= ttm_cutoff:
                        ttm_sum += amt_dec

                    # Determine Dividend Type:
                    # In India, AGM approvals in July/Aug/Sept are usually FINAL, others are INTERIM
                    if dt_date.month in [7, 8, 9]:
                        div_type = "FINAL"
                        type_code = "F"
                    else:
                        div_type = "INTERIM"
                        type_code = "I"

                    # Estimate statutory Payment Date (~25 days after ex-date, SEBI 30-day mandate)
                    payment_date = dt_date + timedelta(days=25)

                    # Historical close price on or before ex-date
                    close_price = None
                    if hist is not None and not hist.empty:
                        try:
                            sub = hist.loc[: dt.strftime("%Y-%m-%d")]
                            if not sub.empty:
                                close_price = float(sub["Close"].iloc[-1])
                        except Exception:
                            close_price = None

                    ref_price = close_price if close_price and close_price > 0 else cur_p_float
                    if ref_price and ref_price > 0:
                        yield_pct = Decimal(str(round((amt_float / ref_price) * 100.0, 2)))
                    else:
                        yield_pct = None

                    status = "UPCOMING" if dt_date > today_date else "PAID"

                    history.append({
                        "ex_date": dt_date,
                        "amount": amt_dec,
                        "type": div_type,
                        "type_code": type_code,
                        "payment_date": payment_date,
                        "yield_pct": yield_pct,
                        "close_price": Decimal(str(round(close_price, 2))) if close_price else None,
                        "status": status,
                    })

                total_count = len(history)
                avg_annual = round(total_5y_payout / Decimal("5.0"), 2) if total_count > 0 else Decimal("0.00")

                if total_count >= 15:
                    freq = "Quarterly"
                elif total_count >= 8:
                    freq = "Semi-Annual"
                elif total_count >= 1:
                    freq = "Annual"
                else:
                    freq = "Sporadic"

                if cur_p_float and cur_p_float > 0 and ttm_sum > 0:
                    ttm_yield = Decimal(str(round((float(ttm_sum) / cur_p_float) * 100.0, 2)))
                else:
                    ttm_yield = None

                summary = {
                    "total_5y_payout": total_5y_payout,
                    "total_5y_count": total_count,
                    "ttm_payout": ttm_sum,
                    "ttm_yield": ttm_yield,
                    "avg_annual_payout": avg_annual,
                    "paying_years": len(years_set),
                    "frequency": freq,
                    "growth_streak": len(years_set),
                }

                cache.set(cache_key, {"history": history, "summary": summary}, timeout=3600)
        except Exception as err:
            logger.warning("Error fetching 5Y dividend history for %s: %s", symbol, err)

        return history, summary
