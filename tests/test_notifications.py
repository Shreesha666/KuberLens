"""
Tests for Notification Center models and views.
"""
import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.notifications.models import Notification, NotificationSeverity


@pytest.mark.django_db
class TestNotificationCenter:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="notifuser",
            email="notifuser@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

    def test_notification_list_view_and_unread_counts(self):
        Notification.objects.create(
            user=self.user,
            title="TCS Crossed Above 4000",
            message="Target reached.",
            severity=NotificationSeverity.SUCCESS,
            is_read=False,
        )
        Notification.objects.create(
            user=self.user,
            title="System Bhavcopy Refreshed",
            message="Data update complete.",
            severity=NotificationSeverity.INFO,
            is_read=True,
            read_at=timezone.now(),
        )

        url = reverse("notifications:list")
        res = self.client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "Notification Center" in content
        assert "TCS Crossed Above 4000" in content
        assert "1 unread" in content

    def test_mark_single_notification_read(self):
        notif = Notification.objects.create(
            user=self.user,
            title="Unread Alert",
            message="Attention needed",
            severity=NotificationSeverity.WARNING,
            is_read=False,
        )

        url = reverse("notifications:mark_read", kwargs={"pk": notif.id})
        res = self.client.post(url)
        assert res.status_code == 302

        notif.refresh_from_db()
        assert notif.is_read is True
        assert notif.read_at is not None

    def test_mark_all_read_and_clear_all(self):
        Notification.objects.create(user=self.user, title="N1", message="M1", is_read=False)
        Notification.objects.create(user=self.user, title="N2", message="M2", is_read=False)

        assert Notification.objects.filter(user=self.user, is_read=False).count() == 2

        # Mark all read
        res_read = self.client.post(reverse("notifications:mark_all_read"))
        assert res_read.status_code == 302
        assert Notification.objects.filter(user=self.user, is_read=False).count() == 0

        # Clear all
        res_clear = self.client.post(reverse("notifications:clear_all"))
        assert res_clear.status_code == 302
        assert Notification.objects.filter(user=self.user).count() == 0
