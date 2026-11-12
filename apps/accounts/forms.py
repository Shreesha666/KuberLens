from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import CustomUser, UserPreference


class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Enter username",
                "autocomplete": "username",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Enter password",
                "autocomplete": "current-password",
            }
        )
    )

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email", "phone_number", "preferred_timezone"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control"}),
            "preferred_timezone": forms.TextInput(attrs={"class": "form-control"}),
        }

class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ["theme", "default_chart_interval", "email_alerts_enabled", "in_app_alerts_enabled"]
        widgets = {
            "theme": forms.Select(attrs={"class": "form-select"}),
            "default_chart_interval": forms.TextInput(attrs={"class": "form-control"}),
            "email_alerts_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "in_app_alerts_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
