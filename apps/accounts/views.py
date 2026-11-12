from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin

from .forms import CustomLoginForm, UserPreferenceForm, UserProfileForm


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
        # Support both GET and POST logout for developer convenience
        logout(request)
        return redirect("accounts:login")

class ProfileView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    template_name = "accounts/profile.html"
    partial_template_name = "accounts/partials/profile_partial.html"
    active_nav = "settings"

    def get(self, request, *args, **kwargs):
        preference = getattr(request.user, "preference", None) or request.user.get_preference()
        user_form = UserProfileForm(instance=request.user)
        preference_form = UserPreferenceForm(instance=preference)
        context = self.get_context_data(
            user_form=user_form,
            preference_form=preference_form,
        )
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        preference = getattr(request.user, "preference", None) or request.user.get_preference()
        user_form = UserProfileForm(request.POST, instance=request.user)
        preference_form = UserPreferenceForm(request.POST, instance=preference)
        if user_form.is_valid() and preference_form.is_valid():
            user_form.save()
            preference_form.save()
            context = self.get_context_data(
                user_form=user_form,
                preference_form=preference_form,
                success_message="Preferences successfully updated.",
            )
            return self.render_to_response(context)
        context = self.get_context_data(
            user_form=user_form,
            preference_form=preference_form,
        )
        return self.render_to_response(context)
