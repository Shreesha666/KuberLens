import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()

@pytest.mark.django_db
def test_custom_user_creation():
    user = User.objects.create_user(
        username="investor1",
        email="investor1@example.com",
        password="TestPassword123!",
        phone_number="+919876543210",
        preferred_timezone="Asia/Kolkata",
    )
    assert user.pk is not None
    assert str(user) == "investor1"
    assert user.phone_number == "+919876543210"
    
    # Assert UserPreference was created automatically via signal
    assert hasattr(user, "preference")
    assert user.preference.theme == "light"
    assert user.preference.default_chart_interval == "1d"

@pytest.mark.django_db
def test_login_and_logout_flow():
    client = Client()
    User.objects.create_user(
        username="trader1",
        password="ValidPassword123!"
    )

    # 1. Access login page
    login_url = reverse("accounts:login")
    res_get = client.get(login_url)
    assert res_get.status_code == 200
    assert "accounts/login.html" in [t.name for t in res_get.templates]

    # 2. Attempt login with invalid password
    res_bad = client.post(login_url, {"username": "trader1", "password": "WrongPassword"})
    assert res_bad.status_code == 200
    assert not res_bad.context["user"].is_authenticated

    # 3. Successful login
    res_good = client.post(login_url, {"username": "trader1", "password": "ValidPassword123!"})
    assert res_good.status_code == 302
    assert res_good.url == reverse("dashboard:index")

    # 4. Verify authenticated session
    res_dash = client.get(reverse("dashboard:index"))
    assert res_dash.status_code == 200
    assert res_dash.context["user"].is_authenticated
    assert res_dash.context["user"].username == "trader1"

    # 5. Logout
    res_logout = client.post(reverse("accounts:logout"))
    assert res_logout.status_code == 302
    assert res_logout.url == reverse("accounts:login")

@pytest.mark.django_db
def test_profile_and_preferences_view():
    client = Client()
    user = User.objects.create_user(
        username="portfolio_mgr",
        email="mgr@example.com",
        password="ValidPassword123!"
    )
    client.force_login(user)

    profile_url = reverse("accounts:profile")
    res_get = client.get(profile_url)
    assert res_get.status_code == 200

    # Update profile & preferences
    res_post = client.post(
        profile_url,
        {
            "first_name": "Ramesh",
            "last_name": "Sharma",
            "email": "ramesh.sharma@example.com",
            "phone_number": "+919999988888",
            "preferred_timezone": "Asia/Kolkata",
            "theme": "dark",
            "default_chart_interval": "1w",
            "email_alerts_enabled": "on",
            "in_app_alerts_enabled": "on",
        }
    )
    assert res_post.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Ramesh"
    assert user.preference.theme == "dark"
    assert user.preference.default_chart_interval == "1w"

@pytest.mark.django_db
def test_unauthenticated_profile_redirect():
    client = Client()
    res = client.get(reverse("accounts:profile"))
    assert res.status_code == 302
    assert "/accounts/login/" in res.url

@pytest.mark.django_db
def test_create_dev_user_command():
    from io import StringIO

    from django.core.management import call_command
    out = StringIO()
    call_command("create_dev_user", username="testadmin", password="TestPass@123", stdout=out)
    assert "Successfully created development superuser 'testadmin'" in out.getvalue()


@pytest.mark.django_db
def test_profile_update_action():
    client = Client()
    user = User.objects.create_user(
        username="trader_pro",
        email="trader@example.com",
        password="ValidPassword123!"
    )
    client.force_login(user)
    profile_url = reverse("accounts:profile")

    res = client.post(
        profile_url,
        {
            "action": "update_profile",
            "first_name": "Shreesha",
            "last_name": "Gundmi",
            "email": "shreesha@example.com",
            "phone_number": "+919876543210",
            "preferred_timezone": "Asia/Kolkata",
        }
    )
    assert res.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Shreesha"
    assert user.last_name == "Gundmi"
    assert user.email == "shreesha@example.com"
    assert user.phone_number == "+919876543210"
    assert "Profile details successfully updated." in res.content.decode()


@pytest.mark.django_db
def test_password_change_action():
    client = Client()
    user = User.objects.create_user(
        username="secure_trader",
        email="secure@example.com",
        password="OldSecurePassword123!"
    )
    client.force_login(user)
    profile_url = reverse("accounts:profile")

    # Post invalid old password
    res_err = client.post(
        profile_url,
        {
            "action": "change_password",
            "old_password": "WrongPassword123!",
            "new_password1": "NewSecurePassword456!",
            "new_password2": "NewSecurePassword456!",
        }
    )
    assert res_err.status_code == 200
    assert "Password change failed" in res_err.content.decode()

    # Post valid password change
    res_ok = client.post(
        profile_url,
        {
            "action": "change_password",
            "old_password": "OldSecurePassword123!",
            "new_password1": "NewSecurePassword456!",
            "new_password2": "NewSecurePassword456!",
        }
    )
    assert res_ok.status_code == 200
    assert "Your password has been changed successfully." in res_ok.content.decode()

    # Verify new password authenticates
    user.refresh_from_db()
    assert user.check_password("NewSecurePassword456!")


@pytest.mark.django_db
def test_reset_paper_account_action():
    from decimal import Decimal
    from apps.paper_trading.models import PaperAccount

    client = Client()
    user = User.objects.create_user(
        username="paper_trader",
        email="paper@example.com",
        password="ValidPassword123!"
    )
    client.force_login(user)

    # Initialize paper account with modified cash balance
    paper_acc, _ = PaperAccount.objects.get_or_create(user=user)
    paper_acc.cash_balance = Decimal("450000.00")
    paper_acc.realized_pnl = Decimal("-50000.00")
    paper_acc.save()

    profile_url = reverse("accounts:profile")
    res = client.post(
        profile_url,
        {
            "action": "reset_paper_account",
        }
    )
    assert res.status_code == 200
    paper_acc.refresh_from_db()
    assert paper_acc.cash_balance == Decimal("1000000.00")
    assert paper_acc.realized_pnl == Decimal("0.00")
    assert "Virtual trading account has been reset" in res.content.decode()


@pytest.mark.django_db
def test_signup_view_flow():
    from decimal import Decimal
    from apps.paper_trading.models import PaperAccount

    client = Client()
    signup_url = reverse("accounts:signup")

    # GET signup page
    res_get = client.get(signup_url)
    assert res_get.status_code == 200
    assert "Create Investor Account" in res_get.content.decode()

    # POST new registration
    res_post = client.post(
        signup_url,
        {
            "username": "newinvestor",
            "first_name": "Arun",
            "last_name": "Kumar",
            "email": "arun.kumar@example.com",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
    )
    assert res_post.status_code == 302
    assert res_post.url == reverse("dashboard:index")

    # Verify user created and auto-logged in
    user = User.objects.get(username="newinvestor")
    assert user.first_name == "Arun"
    assert user.last_name == "Kumar"
    assert user.email == "arun.kumar@example.com"

    # Verify preferences and paper account initialized
    assert hasattr(user, "preference")
    paper_acc = PaperAccount.objects.get(user=user)
    assert paper_acc.cash_balance == Decimal("1000000.00")

    # Verify session is authenticated
    res_dashboard = client.get(reverse("dashboard:index"))
    assert res_dashboard.status_code == 200
    assert user.username in res_dashboard.content.decode()


@pytest.mark.django_db
def test_login_page_renders_signup_link_and_no_guest_link():
    client = Client()
    res = client.get(reverse("accounts:login"))
    assert res.status_code == 200
    content = res.content.decode()
    assert "Continue to Dashboard as Guest" not in content
    assert reverse("accounts:signup") in content


