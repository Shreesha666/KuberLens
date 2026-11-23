from decimal import Decimal

from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin

from .forms import CustomLoginForm, CustomPasswordChangeForm, UserPreferenceForm, UserProfileForm


class LoginView(DjangoLoginView):
    form_class = CustomLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard:index")


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

        context["paper_account"] = paper_acc
        context["holdings_count"] = holdings_count
        context["total_trades"] = total_trades
        context["win_rate"] = round(win_rate, 1)
        context["preference"] = preference
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
            preference_form = UserPreferenceForm(request.POST, instance=preference)
            if preference_form.is_valid():
                preference_form.save()
                success_message = "System preferences successfully updated."
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
