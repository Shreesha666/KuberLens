"""
Backtesting Dashboard and Simulation Views.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from apps.backtesting.models import BacktestRun, BacktestStrategy, StrategyType
from apps.core.mixins import HTMXResponseMixin
from apps.instruments.models import ExchangeListing
from services.backtesting.engine import BacktestEngine

SYSTEM_STRATEGY_DEFAULTS = [
    {
        "name": "SMA 20/50 Golden Cross",
        "description": "Buys when short-term 20-day SMA crosses above medium-term 50-day SMA. Exits on reverse cross, stop-loss, or target.",
        "strategy_type": StrategyType.SMA_CROSSOVER,
        "stop_loss_pct": Decimal("3.50"),
        "target_pct": Decimal("7.00"),
    },
    {
        "name": "RSI Oversold Pullback (<30)",
        "description": "Buys mean-reversion bounces when 14-period RSI exits oversold territory below 35. Exits at 70 RSI or target.",
        "strategy_type": StrategyType.RSI_MEAN_REVERSION,
        "stop_loss_pct": Decimal("3.00"),
        "target_pct": Decimal("6.00"),
    },
    {
        "name": "20-Day High Breakout",
        "description": "Momentum strategy that buys new 20-day high breakouts with volume expansion.",
        "strategy_type": StrategyType.BREAKOUT_MOMENTUM,
        "stop_loss_pct": Decimal("4.00"),
        "target_pct": Decimal("8.00"),
    },
    {
        "name": "MACD Signal Line Cross",
        "description": "Trend-momentum strategy entering when MACD line crosses above the 9-day signal line.",
        "strategy_type": StrategyType.MACD_CROSSOVER,
        "stop_loss_pct": Decimal("3.00"),
        "target_pct": Decimal("6.00"),
    },
]


def ensure_system_strategies():
    """
    Ensures pre-packaged system strategies exist in the database.
    """
    for item in SYSTEM_STRATEGY_DEFAULTS:
        BacktestStrategy.objects.get_or_create(
            name=item["name"],
            defaults={
                "description": item["description"],
                "strategy_type": item["strategy_type"],
                "stop_loss_pct": item["stop_loss_pct"],
                "target_pct": item["target_pct"],
                "is_system_preset": True,
            },
        )


class BacktestDashboardView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Interactive Backtesting Dashboard for configuring and running historical simulations.
    """
    template_name = "backtesting/dashboard.html"
    partial_template_name = "backtesting/partials/dashboard_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ensure_system_strategies()

        user = self.request.user
        strategies = BacktestStrategy.objects.all()
        recent_runs = BacktestRun.objects.filter(user=user).select_related(
            "strategy", "listing__instrument"
        ).order_by("-created_at")[:10]

        # Top tradeable listings
        popular_listings = ExchangeListing.objects.filter(
            is_tradeable=True, is_primary=True
        ).select_related("instrument")[:30]

        active_run = None
        run_id = self.request.GET.get("run_id")
        if run_id:
            active_run = BacktestRun.objects.filter(id=run_id, user=user).first()
        elif recent_runs.exists():
            active_run = recent_runs.first()

        context["active_nav"] = "strategy_backtesting"
        context["strategies"] = strategies
        context["recent_runs"] = recent_runs
        context["popular_listings"] = popular_listings
        context["active_run"] = active_run
        return context

    def post(self, request, *args, **kwargs):
        ensure_system_strategies()

        user = request.user
        strat_id = request.POST.get("strategy_id")
        symbol = request.POST.get("symbol", "RELIANCE").strip().upper()
        capital_str = request.POST.get("initial_capital", "100000")
        sl_str = request.POST.get("stop_loss_pct", "3.0")
        tp_str = request.POST.get("target_pct", "6.0")
        slip_str = request.POST.get("slippage_pct", "0.05")
        comm_str = request.POST.get("brokerage_pct", "0.03")

        strategy = get_object_or_404(BacktestStrategy, pk=strat_id)
        listing = get_object_or_404(ExchangeListing, symbol=symbol, is_tradeable=True)

        try:
            capital = Decimal(capital_str)
            sl_pct = Decimal(sl_str)
            tp_pct = Decimal(tp_str)
            slip_pct = Decimal(slip_str)
            comm_pct = Decimal(comm_str)
        except Exception:
            capital = Decimal("100000.00")
            sl_pct = Decimal("3.00")
            tp_pct = Decimal("6.00")
            slip_pct = Decimal("0.050")
            comm_pct = Decimal("0.030")

        today = timezone.now().date()
        start_date = today - timedelta(days=365)

        try:
            run = BacktestEngine.run_simulation(
                user=user,
                strategy=strategy,
                listing=listing,
                start_date=start_date,
                end_date=today,
                initial_capital=capital,
                stop_loss_pct=sl_pct,
                target_pct=tp_pct,
                slippage_pct=slip_pct,
                brokerage_pct=comm_pct,
            )
            messages.success(request, f"Backtest completed: {run.total_return_pct:+}% Return across {run.total_trades} trades.")
            return redirect(f"/backtesting/?run_id={run.id}")
        except Exception as e:
            messages.error(request, f"Backtest failed: {e}")
            return redirect("backtesting:dashboard")


class BacktestRunDetailView(LoginRequiredMixin, HTMXResponseMixin, DetailView):
    """
    Detailed trade breakdown for a specific backtest execution.
    """
    model = BacktestRun
    template_name = "backtesting/run_detail.html"
    partial_template_name = "backtesting/partials/run_detail_partial.html"
    context_object_name = "run"

    def get_queryset(self):
        return BacktestRun.objects.filter(user=self.request.user).select_related(
            "strategy", "listing__instrument"
        )
