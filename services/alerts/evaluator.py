"""
Alert Evaluator Engine.
Evaluates active price, technical, and portfolio alert rules against latest quotes and snapshots.
Enforces deduplication cooldowns and market-hours filtering according to Master Specification Section 20.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.alerts.models import AlertRule, AlertType
from apps.holdings.models import Holding
from apps.market.models import HistoricalCandle, MarketQuote
from apps.notifications.models import Notification, NotificationSeverity
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.calendar.exchange_calendar import ExchangeCalendar

logger = logging.getLogger(__name__)


class AlertEvaluator:
    """
    Evaluator engine for user alert rules.
    """

    @classmethod
    def evaluate_alert(cls, alert: AlertRule, check_market_hours: bool = True) -> bool:
        """
        Evaluates a single alert rule against current market data.
        Returns True if triggered and notification created, False otherwise.
        """
        if not alert.is_active:
            return False

        # Market-hours check
        if check_market_hours and alert.is_market_hours_only:
            session = ExchangeCalendar.get_session_status()
            if not session.is_open:
                return False

        # Cooldown check: prevent duplicate notifications for unchanged conditions
        now = timezone.now()
        if alert.last_triggered_at:
            cooldown_period = timedelta(minutes=alert.cooldown_minutes)
            if now - alert.last_triggered_at < cooldown_period:
                return False

        listing = alert.listing
        quote = MarketQuote.objects.filter(listing=listing).first() if listing else None
        tech_snap = TechnicalIndicatorSnapshot.objects.filter(listing=listing).first() if listing else None

        triggered = False
        title = ""
        message = ""
        severity = NotificationSeverity.INFO
        link_url = f"/stocks/{listing.symbol}/" if listing else "/portfolio/"

        alert_type = alert.alert_type
        target = alert.target_value or Decimal("0")

        # 1. Price Alerts
        if alert_type == AlertType.PRICE_ABOVE and quote:
            if quote.price >= target:
                triggered = True
                title = f"{listing.symbol} Crossed Above ₹{target:.2f}"
                message = f"{listing.instrument.display_name} has traded at ₹{quote.price:.2f}, crossing above your alert threshold of ₹{target:.2f}."
                severity = NotificationSeverity.SUCCESS

        elif alert_type == AlertType.PRICE_BELOW and quote:
            if quote.price <= target:
                triggered = True
                title = f"{listing.symbol} Fell Below ₹{target:.2f}"
                message = f"{listing.instrument.display_name} has dropped to ₹{quote.price:.2f}, falling below your alert threshold of ₹{target:.2f}."
                severity = NotificationSeverity.WARNING

        elif alert_type == AlertType.PERCENT_MOVE and quote:
            if abs(quote.change_percent) >= target:
                triggered = True
                direction = "gained" if quote.change_percent > 0 else "fallen"
                title = f"{listing.symbol} Moved {quote.change_percent:+.2f}% Today"
                message = f"{listing.instrument.display_name} has {direction} by {abs(quote.change_percent):.2f}%, exceeding your {target:.2f}% daily move alert."
                severity = NotificationSeverity.INFO

        elif alert_type == AlertType.BREAKOUT_52W_HIGH and quote:
            high_52w = HistoricalCandle.objects.filter(
                listing=listing, interval="1d", timestamp__gte=now - timedelta(days=365)
            ).aggregate(models.Max("high"))["high__max"]
            if high_52w and quote.price >= high_52w:
                triggered = True
                title = f"{listing.symbol} 52-Week High Breakout (₹{quote.price:.2f})"
                message = f"{listing.instrument.display_name} hit a new 52-week high of ₹{quote.price:.2f} (prev high: ₹{high_52w:.2f})."
                severity = NotificationSeverity.SUCCESS

        elif alert_type == AlertType.BREAKDOWN_52W_LOW and quote:
            low_52w = HistoricalCandle.objects.filter(
                listing=listing, interval="1d", timestamp__gte=now - timedelta(days=365)
            ).aggregate(models.Min("low"))["low__min"]
            if low_52w and quote.price <= low_52w:
                triggered = True
                title = f"{listing.symbol} 52-Week Low Breakdown (₹{quote.price:.2f})"
                message = f"{listing.instrument.display_name} dropped to a new 52-week low of ₹{quote.price:.2f}."
                severity = NotificationSeverity.DANGER

        # 2. Technical Alerts
        elif alert_type == AlertType.RSI_OVERSOLD and tech_snap:
            if tech_snap.rsi_14 is not None and tech_snap.rsi_14 <= target:
                triggered = True
                title = f"{listing.symbol} 14-Period RSI Oversold ({tech_snap.rsi_14:.1f})"
                message = f"RSI for {listing.symbol} reached {tech_snap.rsi_14:.1f}, crossing below the oversold threshold of {target:.1f}."
                severity = NotificationSeverity.INFO

        elif alert_type == AlertType.RSI_OVERBOUGHT and tech_snap:
            if tech_snap.rsi_14 is not None and tech_snap.rsi_14 >= target:
                triggered = True
                title = f"{listing.symbol} 14-Period RSI Overbought ({tech_snap.rsi_14:.1f})"
                message = f"RSI for {listing.symbol} reached {tech_snap.rsi_14:.1f}, crossing above the overbought threshold of {target:.1f}."
                severity = NotificationSeverity.WARNING

        elif alert_type == AlertType.MACD_BULLISH_CROSS and tech_snap:
            if tech_snap.macd_line is not None and tech_snap.macd_signal is not None:
                if tech_snap.macd_line > tech_snap.macd_signal:
                    triggered = True
                    title = f"{listing.symbol} MACD Bullish Crossover"
                    message = f"MACD line ({tech_snap.macd_line:.2f}) crossed above signal line ({tech_snap.macd_signal:.2f}) for {listing.symbol}."
                    severity = NotificationSeverity.SUCCESS

        elif alert_type == AlertType.MACD_BEARISH_CROSS and tech_snap:
            if tech_snap.macd_line is not None and tech_snap.macd_signal is not None:
                if tech_snap.macd_line < tech_snap.macd_signal:
                    triggered = True
                    title = f"{listing.symbol} MACD Bearish Crossover"
                    message = f"MACD line ({tech_snap.macd_line:.2f}) dropped below signal line ({tech_snap.macd_signal:.2f}) for {listing.symbol}."
                    severity = NotificationSeverity.WARNING

        elif alert_type == AlertType.SMA_CROSSOVER and tech_snap:
            if tech_snap.sma_20 and tech_snap.sma_50 and tech_snap.sma_20 > tech_snap.sma_50:
                triggered = True
                title = f"{listing.symbol} 20 SMA Crossed Above 50 SMA"
                message = f"Short-term 20 SMA (₹{tech_snap.sma_20:.2f}) crossed above medium-term 50 SMA (₹{tech_snap.sma_50:.2f})."
                severity = NotificationSeverity.SUCCESS

        elif alert_type == AlertType.SMA_BEARISH_CROSS and tech_snap:
            if tech_snap.sma_20 and tech_snap.sma_50 and tech_snap.sma_20 < tech_snap.sma_50:
                triggered = True
                title = f"{listing.symbol} 20 SMA Crossed Below 50 SMA"
                message = f"Short-term 20 SMA (₹{tech_snap.sma_20:.2f}) dropped below medium-term 50 SMA (₹{tech_snap.sma_50:.2f})."
                severity = NotificationSeverity.WARNING

        elif alert_type == AlertType.GOLDEN_CROSS and tech_snap:
            if tech_snap.sma_50 and tech_snap.sma_200 and tech_snap.sma_50 > tech_snap.sma_200:
                triggered = True
                title = f"GOLDEN CROSS: {listing.symbol} (50 SMA > 200 SMA)"
                message = f"{listing.instrument.display_name} confirmed a Golden Cross with 50 SMA (₹{tech_snap.sma_50:.2f}) above 200 SMA (₹{tech_snap.sma_200:.2f})."
                severity = NotificationSeverity.SUCCESS

        elif alert_type == AlertType.DEATH_CROSS and tech_snap:
            if tech_snap.sma_50 and tech_snap.sma_200 and tech_snap.sma_50 < tech_snap.sma_200:
                triggered = True
                title = f"DEATH CROSS: {listing.symbol} (50 SMA < 200 SMA)"
                message = f"{listing.instrument.display_name} confirmed a Death Cross with 50 SMA (₹{tech_snap.sma_50:.2f}) falling below 200 SMA (₹{tech_snap.sma_200:.2f})."
                severity = NotificationSeverity.DANGER

        elif alert_type == AlertType.VOLUME_SPIKE and quote and tech_snap:
            mult = float(target) if target > 0 else 2.0
            if tech_snap.volume_sma_20 and quote.volume >= (mult * tech_snap.volume_sma_20):
                triggered = True
                title = f"VOLUME SURGE: {listing.symbol} ({quote.volume:,} shares)"
                message = f"{listing.symbol} volume spiked to {quote.volume:,}, exceeding {mult:.1f}× its 20-day average volume ({tech_snap.volume_sma_20:,})."
                severity = NotificationSeverity.INFO

        elif alert_type == AlertType.BOLLINGER_UPPER_BREAK and quote and tech_snap:
            if tech_snap.bollinger_upper and quote.price >= tech_snap.bollinger_upper:
                triggered = True
                title = f"{listing.symbol} Pierced Upper Bollinger Band"
                message = f"{listing.symbol} price (₹{quote.price:.2f}) reached or exceeded its Upper Bollinger Band (₹{tech_snap.bollinger_upper:.2f})."
                severity = NotificationSeverity.INFO

        elif alert_type == AlertType.BOLLINGER_LOWER_BREAK and quote and tech_snap:
            if tech_snap.bollinger_lower and quote.price <= tech_snap.bollinger_lower:
                triggered = True
                title = f"{listing.symbol} Pierced Lower Bollinger Band"
                message = f"{listing.symbol} price (₹{quote.price:.2f}) touched or dropped below its Lower Bollinger Band (₹{tech_snap.bollinger_lower:.2f})."
                severity = NotificationSeverity.WARNING

        # 3. Portfolio Alerts
        elif alert_type == AlertType.PORTFOLIO_STOP_LOSS and listing and quote:
            holding = Holding.objects.filter(portfolio__user=alert.user, listing=listing, total_quantity__gt=0).first()
            if holding and quote.price <= target:
                triggered = True
                title = f"PORTFOLIO STOP LOSS: {listing.symbol} @ ₹{quote.price:.2f}"
                message = f"Your holding in {listing.symbol} ({holding.total_quantity} shares) reached stop loss price ₹{target:.2f}. Review exit rules."
                severity = NotificationSeverity.DANGER
                link_url = "/portfolio/holdings/"

        elif alert_type == AlertType.PORTFOLIO_TARGET and listing and quote:
            holding = Holding.objects.filter(portfolio__user=alert.user, listing=listing, total_quantity__gt=0).first()
            if holding and quote.price >= target:
                triggered = True
                title = f"PROFIT TARGET REACHED: {listing.symbol} @ ₹{quote.price:.2f}"
                message = f"{listing.symbol} reached your target price ₹{target:.2f}. Consider securing gains."
                severity = NotificationSeverity.SUCCESS
                link_url = "/portfolio/holdings/"

        elif alert_type == AlertType.CONCENTRATION_THRESHOLD and listing:
            holding = Holding.objects.filter(portfolio__user=alert.user, listing=listing, total_quantity__gt=0).first()
            if holding:
                all_holdings = Holding.objects.filter(portfolio__user=alert.user, total_quantity__gt=0)
                tot_val = sum(float(h.current_value) for h in all_holdings)
                c_val = float(holding.current_value) if holding.current_value else float(holding.total_quantity * (quote.price if quote else holding.average_buy_price))
                weight = (c_val / tot_val * 100) if tot_val > 0 else 0.0

                thresh = float(target) if target > 0 else 15.0
                if weight >= thresh:
                    triggered = True
                    title = f"High Portfolio Concentration: {listing.symbol} ({weight:.1f}%)"
                    message = f"{listing.symbol} represents {weight:.1f}% of your portfolio, exceeding safe concentration threshold of {thresh:.1f}%."
                    severity = NotificationSeverity.WARNING
                    link_url = "/portfolio/"

        if triggered:
            # Create in-app notification
            Notification.objects.create(
                user=alert.user,
                alert_rule=alert,
                title=title,
                message=message,
                severity=severity,
                link_url=link_url,
            )

            # Update alert state and audit counters
            alert.last_triggered_at = now
            alert.trigger_count += 1
            alert.save(update_fields=["last_triggered_at", "trigger_count"])
            logger.info("Alert triggered for user %s: %s", alert.user.username, title)
            return True

        return False

    @classmethod
    def evaluate_all_active_alerts(cls, user=None, check_market_hours: bool = False) -> int:
        """
        Evaluates all active alerts in the system or for a specific user.
        Returns total number of alerts triggered.
        """
        qs = AlertRule.objects.filter(is_active=True).select_related("listing__instrument", "user")
        if user:
            qs = qs.filter(user=user)

        triggered_count = 0
        for alert in qs:
            try:
                if cls.evaluate_alert(alert, check_market_hours=check_market_hours):
                    triggered_count += 1
            except Exception as e:
                logger.error("Error evaluating alert ID %s: %s", alert.id, e)

        return triggered_count
