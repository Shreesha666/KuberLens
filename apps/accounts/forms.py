from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

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


class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email", "phone_number", "preferred_timezone"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@example.com"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "+91 98765 43210"}),
            "preferred_timezone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Asia/Kolkata"}),
        }


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ["theme", "default_chart_interval", "email_alerts_enabled", "in_app_alerts_enabled"]
        widgets = {
            "theme": forms.Select(attrs={"class": "form-select"}),
            "default_chart_interval": forms.Select(
                choices=[
                    ("1m", "1 Minute (Intraday)"),
                    ("5m", "5 Minutes (Intraday)"),
                    ("15m", "15 Minutes (Swing)"),
                    ("1d", "1 Day (Daily Standard)"),
                    ("1w", "1 Week (Weekly Structure)"),
                ],
                attrs={"class": "form-select"}
            ),
            "email_alerts_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "in_app_alerts_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
