"""
Notification Center Views.
Allows users to view in-app alert notifications, mark them as read, and clear history.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.notifications.models import Notification


class NotificationListView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    In-App Notification Center displaying triggered alerts and system warnings.
    """
    template_name = "notifications/list.html"
    partial_template_name = "notifications/partials/list_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        qs = Notification.objects.filter(user=user).select_related("alert_rule__listing")

        # Paginate (15 notifications per page)
        page_number = self.request.GET.get("page", 1)
        paginator = Paginator(qs, 15)
        page_obj = paginator.get_page(page_number)

        unread_count = Notification.objects.filter(user=user, is_read=False).count()

        context["active_nav"] = "notifications"
        context["page_obj"] = page_obj
        context["notifications"] = page_obj.object_list
        context["unread_count"] = unread_count
        context["total_count"] = paginator.count
        return context


class NotificationMarkReadView(LoginRequiredMixin, View):
    """
    Marks a single notification as read.
    """
    def post(self, request, pk: int, *args, **kwargs):
        notif = get_object_or_404(Notification, pk=pk, user=request.user)
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=["is_read", "read_at"])
        return redirect("notifications:list")


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    """
    Marks all notifications for the current user as read.
    """
    def post(self, request, *args, **kwargs):
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        messages.success(request, "All notifications marked as read.")
        return redirect("notifications:list")


class NotificationDeleteView(LoginRequiredMixin, View):
    """
    Deletes a single notification.
    """
    def post(self, request, pk: int, *args, **kwargs):
        notif = get_object_or_404(Notification, pk=pk, user=request.user)
        notif.delete()
        return redirect("notifications:list")


class NotificationClearAllView(LoginRequiredMixin, View):
    """
    Clears all notifications for the current user.
    """
    def post(self, request, *args, **kwargs):
        count = Notification.objects.filter(user=request.user).delete()[0]
        messages.info(request, f"Cleared {count} notifications.")
        return redirect("notifications:list")

