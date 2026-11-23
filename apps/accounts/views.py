from decimal import Decimal

from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, TemplateView

from apps.core.mixins import HTMXResponseMixin

from .forms import (
    CustomLoginForm,
    CustomPasswordChangeForm,
    CustomUserCreationForm,
    UserPreferenceForm,
    UserProfileForm,
)


class LoginView(DjangoLoginView):
    form_class = CustomLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard:index")


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("dashboard:index")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard:index")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        user.get_preference()
        from apps.paper_trading.models import PaperAccount
        PaperAccount.objects.get_or_create(user=user)
        login(self.request, user)
        return redirect(self.success_url)


class LogoutView(View):
    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("accounts:login")

    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect("accounts:login")


class ProfileView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    template_name = "accounts/profile.html"
    partial_template_name = "accounts/partials/profile_partial.html"
    active_nav = "settings"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        preference = getattr(user, "preference", None) or user.get_preference()

        context.setdefault("user_form", UserProfileForm(instance=user))
        context.setdefault("preference_form", UserPreferenceForm(instance=preference))
        context.setdefault("password_form", CustomPasswordChangeForm(user=user))

        # Paper Account Overview & Stats
        from decimal import Decimal
        from django.utils import timezone
        from apps.holdings.models import Holding
        from apps.paper_trading.models import PaperAccount, PaperTrade

        paper_acc = PaperAccount.objects.filter(user=user).first()
        holdings_count = Holding.objects.filter(portfolio__user=user).count()

        total_trades = PaperTrade.objects.filter(account=paper_acc).count() if paper_acc else 0
        winning_trades = (
            PaperTrade.objects.filter(account=paper_acc, net_realized_pnl__gt=0).count()
            if paper_acc else 0
        )
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        realized_pnl = paper_acc.realized_pnl if paper_acc else Decimal("0.00")
        portfolio_value = paper_acc.total_portfolio_value if paper_acc else Decimal("1000000.00")

        # Trader XP, Level & Milestones
        # Base 50 XP + 30 XP per trade + 20 XP per holding + 100 XP if profitable
        trader_xp = 50 + (total_trades * 30) + (holdings_count * 20) + (100 if realized_pnl > 0 else 0)

        if trader_xp < 300:
            level_num = 1
            level_name = "Retail Trader"
            next_level_name = "Swing Trader"
            next_level_xp = 300
            current_level_min = 0
        elif trader_xp < 800:
            level_num = 2
            level_name = "Swing Trader"
            next_level_name = "Day Trader"
            next_level_xp = 800
            current_level_min = 300
        elif trader_xp < 2000:
            level_num = 3
            level_name = "Day Trader"
            next_level_name = "Desk Pro Trader"
            next_level_xp = 2000
            current_level_min = 800
        else:
            level_num = 4
            level_name = "Desk Pro Trader"
            next_level_name = "Master Trader"
            next_level_xp = 5000
            current_level_min = 2000

        xp_range = max(1, next_level_xp - current_level_min)
        xp_progress = min(100, max(0, int(((trader_xp - current_level_min) / xp_range) * 100)))
        xp_needed = max(0, next_level_xp - trader_xp)

        # 8 Achievements
        milestones = [
            {
                "id": "first_trade",
                "title": "First Execution",
                "desc": "Placed your first paper order",
                "icon": "bi-rocket-takeoff-fill",
                "unlocked": total_trades >= 1,
            },
            {
                "id": "portfolio_starter",
                "title": "Asset Collector",
                "desc": "Held 3+ active positions",
                "icon": "bi-briefcase-fill",
                "unlocked": holdings_count >= 3,
            },
            {
                "id": "in_the_green",
                "title": "In The Green",
                "desc": "Positive realized returns",
                "icon": "bi-graph-up-arrow",
                "unlocked": realized_pnl > 0,
            },
            {
                "id": "market_active",
                "title": "Active Execution",
                "desc": "Executed 5+ paper trades",
                "icon": "bi-lightning-charge-fill",
                "unlocked": total_trades >= 5,
            },
            {
                "id": "diversified",
                "title": "Diversified Vault",
                "desc": "Held 10+ active positions",
                "icon": "bi-pie-chart-fill",
                "unlocked": holdings_count >= 10,
            },
            {
                "id": "high_win_rate",
                "title": "Sniper Precision",
                "desc": "Win rate > 50% (min 3 trades)",
                "icon": "bi-bullseye",
                "unlocked": win_rate >= 50.0 and total_trades >= 3,
            },
            {
                "id": "century_club",
                "title": "Centurion",
                "desc": "Executed 20+ paper trades",
                "icon": "bi-trophy-fill",
                "unlocked": total_trades >= 20,
            },
            {
                "id": "capital_growth",
                "title": "Alpha Generator",
                "desc": "Portfolio value > ₹10,00,000",
                "icon": "bi-gem",
                "unlocked": portfolio_value > Decimal("1000000.00"),
            },
        ]
        unlocked_count = sum(1 for m in milestones if m["unlocked"])

        # Clean Account Age
        delta = timezone.now() - user.date_joined
        if delta.days == 0:
            account_age_str = "Today"
        elif delta.days == 1:
            account_age_str = "1 Day"
        elif delta.days < 30:
            account_age_str = f"{delta.days} Days"
        elif delta.days < 365:
            months = delta.days // 30
            account_age_str = f"{months} Mo{'s' if months > 1 else ''}"
        else:
            years = delta.days // 365
            account_age_str = f"{years} Yr{'s' if years > 1 else ''}"

        context["paper_account"] = paper_acc
        context["holdings_count"] = holdings_count
        context["total_trades"] = total_trades
        context["win_rate"] = round(win_rate, 1)
        context["preference"] = preference
        context["trader_xp"] = trader_xp
        context["level_num"] = level_num
        context["level_name"] = level_name
        context["next_level_name"] = next_level_name
        context["next_level_xp"] = next_level_xp
        context["xp_progress"] = xp_progress
        context["xp_needed"] = xp_needed
        context["milestones"] = milestones
        context["unlocked_count"] = unlocked_count
        context["account_age_str"] = account_age_str
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        user = request.user
        preference = getattr(user, "preference", None) or user.get_preference()

        user_form = UserProfileForm(instance=user)
        preference_form = UserPreferenceForm(instance=preference)
        password_form = CustomPasswordChangeForm(user=user)
        success_message = None
        error_message = None

        if action == "change_password":
            password_form = CustomPasswordChangeForm(user=user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                password_form = CustomPasswordChangeForm(user=user)
                success_message = "Your password has been changed successfully."
            else:
                error_message = "Password change failed. Please review the errors below."

        elif action == "update_profile":
            user_form = UserProfileForm(request.POST, instance=user)
            if user_form.is_valid():
                user_form.save()
                success_message = "Profile details successfully updated."
            else:
                error_message = "Please correct the errors in the profile form."

        elif action == "update_preferences":
            updated_any = False
            for field in ["theme", "default_chart_interval", "email_alerts_enabled", "in_app_alerts_enabled"]:
                if field in request.POST:
                    val = request.POST.get(field)
                    if field in ["email_alerts_enabled", "in_app_alerts_enabled"]:
                        setattr(preference, field, val in ["true", "True", "on", "1", True])
                    else:
                        setattr(preference, field, val)
                    updated_any = True
            if updated_any:
                preference.save()
                preference_form = UserPreferenceForm(instance=preference)
                success_message = "Preferences updated."
            else:
                preference_form = UserPreferenceForm(request.POST, instance=preference)
                if preference_form.is_valid():
                    preference_form.save()
                    success_message = "Preferences updated."
                else:
                    error_message = "Please check your preferences input."

        elif action == "reset_paper_account":
            from apps.paper_trading.models import PaperAccount
            paper_acc = PaperAccount.objects.filter(user=user).first()
            if paper_acc:
                paper_acc.reset_account()
                success_message = "Virtual trading account has been reset to ₹10,00,000.00."

        else:
            # Combined / default update (backward compatible with original form)
            user_form = UserProfileForm(request.POST, instance=user)
            preference_form = UserPreferenceForm(request.POST, instance=preference)
            if user_form.is_valid() and preference_form.is_valid():
                user_form.save()
                preference_form.save()
                success_message = "Preferences and profile successfully updated."
            else:
                error_message = "Please correct the form errors."

        context = self.get_context_data(
            user_form=user_form,
            preference_form=preference_form,
            password_form=password_form,
            success_message=success_message,
            error_message=error_message,
        )
        return self.render_to_response(context)
